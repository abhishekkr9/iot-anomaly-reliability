import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _required_any(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    joined = ", ".join(names)
    raise ValueError(f"Missing required environment variable. Set one of: {joined}")


PROJECT_ID = _required_any("PROJECT_ID", "GOOGLE_CLOUD_PROJECT")
REGION = os.getenv("REGION", "us-central1")

DATASET_ID = os.getenv("DATASET_ID", "iot_sensor_data")
TABLE_ID = os.getenv("TABLE_ID", "raw_telemetry")
TRAINING_LOOKBACK_DAYS = int(os.getenv("TRAINING_LOOKBACK_DAYS", "30"))

INPUT_TOPIC_ID = os.getenv("INPUT_TOPIC_ID", "telemetry-stream")
OUTPUT_TOPIC_ID = os.getenv("OUTPUT_TOPIC_ID", "anomaly-events")
INPUT_TOPIC = f"projects/{PROJECT_ID}/topics/{INPUT_TOPIC_ID}"
OUTPUT_TOPIC = f"projects/{PROJECT_ID}/topics/{OUTPUT_TOPIC_ID}"

BUCKET_NAME = os.getenv("BUCKET_NAME", "")
MODEL_DIR = os.getenv("MODEL_DIR", "vertex-models/isolation-forest/v1")
ENDPOINT_ID = _required("ENDPOINT_ID")

# ── Automated Retraining Configuration ────────────────────────────────────────
RETRAIN_ENABLED = os.getenv("RETRAIN_ENABLED", "false").lower() == "true"
RETRAIN_QUERY_LIMIT = int(os.getenv("RETRAIN_QUERY_LIMIT", "20000"))
RETRAIN_MIN_ROWS = int(os.getenv("RETRAIN_MIN_ROWS", "100"))
RETRAIN_MODEL_DISPLAY_NAME = os.getenv("RETRAIN_MODEL_DISPLAY_NAME", "iot-anomaly-model-retrained")
RETRAIN_GCS_MODEL_DIR = os.getenv("RETRAIN_GCS_MODEL_DIR", "vertex-models/isolation-forest/retrain")

SERVING_SKLEARN_MAJOR_MINOR = os.getenv("SERVING_SKLEARN_MAJOR_MINOR", "1.5")
SERVING_CONTAINER_URI = os.getenv(
    "SERVING_CONTAINER_URI",
    "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-5:latest",
)

FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "iot-anomalies")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CREWAI_MODEL = os.getenv("CREWAI_MODEL", "gemini/gemini-2.5-flash")
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "60"))
WINDOW_SLIDE = int(os.getenv("WINDOW_SLIDE", "10"))
