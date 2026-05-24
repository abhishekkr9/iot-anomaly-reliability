import logging

from crewai import Agent, Crew, LLM, Task
from crewai.tools import tool
from google.cloud import bigquery, firestore

# pyrefly: ignore [missing-import]
from src.core.config import (
    CREWAI_MODEL,
    DATASET_ID,
    FIRESTORE_DATABASE,
    GEMINI_API_KEY,
    PROJECT_ID,
    REGION,
    TABLE_ID,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM + GCP clients
# ---------------------------------------------------------------------------
import os

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", REGION)
if GEMINI_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

llm = LLM(model=CREWAI_MODEL, temperature=0.2)

bq_client = bigquery.Client(project=PROJECT_ID)
db = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)


# ---------------------------------------------------------------------------
# CrewAI tools
# ---------------------------------------------------------------------------
@tool("fetch_sensor_history")
def fetch_sensor_history(sensor_id: str) -> str:
    """Fetches the last 5 readings for a specific sensor from BigQuery to see if it was trending up."""
    logger.info("[Tool] Fetching BigQuery history for %s", sensor_id)
    try:
        query = f"""
            SELECT timestamp, metric_value
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
            WHERE sensor_id = @sensor_id
              AND metric_name = 'temperature'
              AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            ORDER BY timestamp DESC LIMIT 5
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("sensor_id", "STRING", sensor_id)
            ]
        )
        df = bq_client.query(query, job_config=job_config).to_dataframe()
        if df.empty:
            return "No recent history found."
        return f"Recent history for {sensor_id}:\n{df.to_string(index=False)}"
    except Exception as exc:
        return f"Error fetching data: {exc}"


# ---------------------------------------------------------------------------
# Background investigation task
# ---------------------------------------------------------------------------
def investigate_anomaly(anomaly_data: dict) -> None:
    """Runs a CrewAI investigation in the background and persists the report to Firestore."""
    sensor_id = anomaly_data.get("sensor_id", "UNKNOWN")
    anomaly_reason = anomaly_data.get("anomaly_reason", "Unknown reason")
    metric_value = anomaly_data.get("metric_value", "N/A")

    logger.info("[Agent] Starting investigation for %s (value=%s)", sensor_id, metric_value)

    try:
        engineer = Agent(
            role="Senior Reliability Engineer",
            goal="Diagnose IoT sensor anomalies and write a brief executive summary of the root cause.",
            backstory=(
                "You are an expert at analyzing industrial sensor data. "
                "You always check the recent history to see if a spike was sudden or gradual."
            ),
            verbose=True,
            llm=llm,
            tools=[fetch_sensor_history],
        )

        task = Task(
            description=f"""
            An anomaly was just detected on sensor: {sensor_id}.
            The ML model reported: "{anomaly_reason}".

            Steps:
            1. Use your tool to fetch the recent history for this sensor.
            2. Analyse if this was a sudden massive spike or a gradual heat-up.
            3. Write a 3-sentence diagnostic report. End with a recommendation
               (e.g. "Dispatch technician" or "Monitor closely").
            """,
            expected_output="A short 3-sentence diagnostic report.",
            agent=engineer,
        )

        crew = Crew(agents=[engineer], tasks=[task])
        result = crew.kickoff()

        logger.info("[Agent] Investigation complete for %s:\n%s", sensor_id, result)

        db.collection("anomalies").document().set(
            {
                "sensor_id": sensor_id,
                "metric_value": metric_value,
                "ml_reason": anomaly_reason,
                "ai_report": str(result),
                "timestamp": firestore.SERVER_TIMESTAMP,
            }
        )
        logger.info("[Agent] Saved AI report to Firestore for %s", sensor_id)

    except Exception:
        logger.exception("[Agent] Investigation failed for %s", sensor_id)
