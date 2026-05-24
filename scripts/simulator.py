"""
Pub/Sub telemetry simulator — publishes synthetic sensor readings to GCP.

Usage:
    python -m scripts.simulator
"""
import json
import logging
import random
import time
from datetime import datetime, timezone

from google.cloud.pubsub_v1 import PublisherClient

# pyrefly: ignore [missing-import]
from src.core.config import INPUT_TOPIC_ID, PROJECT_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

publisher = PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, INPUT_TOPIC_ID)


def generate_sensor_data() -> dict:
    """Generates a synthetic sensor reading. Injects occasional spikes (~5 % of the time)."""
    is_spike = random.random() < 0.05
    metric_value = (
        round(random.uniform(85.0, 110.0), 2) if is_spike else round(random.uniform(50.0, 80.0), 2)
    )
    return {
        "sensor_id": f"SENSOR_{random.randint(1, 3)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric_name": "temperature",
        "metric_value": metric_value,
        "status": "ONLINE",
    }


def main() -> None:
    logger.info("Simulator started — publishing to %s. Press Ctrl+C to stop.", topic_path)
    try:
        while True:
            record = generate_sensor_data()
            payload = json.dumps(record).encode("utf-8")
            message_id = publisher.publish(topic_path, payload).result()
            logger.info("Published [%s]: %s", message_id, record)
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise


if __name__ == "__main__":
    main()
