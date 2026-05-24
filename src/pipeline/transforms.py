import datetime
import json
import logging

import apache_beam as beam

# pyrefly: ignore [missing-import]
from src.core.config import ENDPOINT_ID, PROJECT_ID, REGION


class ParseAndKey(beam.DoFn):
    """Decodes raw Pub/Sub bytes and keys each record by sensor_id."""

    def process(self, element):
        try:
            data = json.loads(element.decode("utf-8"))
            yield (data["sensor_id"], data)
        except Exception as exc:
            logging.error("Failed to parse message: %s", exc)


class DetectAnomalyML(beam.DoFn):
    """Calls a Vertex AI Endpoint to classify each windowed reading as normal or anomalous."""

    def setup(self):
        """Initialises the Vertex AI client once per Dataflow worker."""
        from google.cloud import aiplatform

        aiplatform.init(project=PROJECT_ID, location=REGION)
        self.endpoint = aiplatform.Endpoint(ENDPOINT_ID)

    def process(self, element, window_param=beam.DoFn.WindowParam):
        sensor_id, readings = element
        readings = list(readings)

        if len(readings) < 5:
            return

        latest_reading = max(readings, key=lambda x: x["timestamp"])

        dt = datetime.datetime.fromisoformat(
            latest_reading["timestamp"].replace("Z", "+00:00")
        )
        hour = dt.hour
        metric_value = latest_reading["metric_value"]

        instances = [[metric_value, hour]]

        try:
            response = self.endpoint.predict(instances=instances)
            prediction = response.predictions[0]  # 1 = normal, -1 = anomaly

            if int(prediction) == -1:
                latest_reading["anomaly_reason"] = (
                    f"Vertex AI ML Model flagged {metric_value} at hour {hour} as an anomaly!"
                )
                yield json.dumps(latest_reading).encode("utf-8")

        except Exception as exc:
            logging.error("Vertex AI prediction failed: %s", exc)
