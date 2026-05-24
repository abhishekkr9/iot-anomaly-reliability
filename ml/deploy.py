"""
Upload a trained model artifact to GCS and deploy it to a Vertex AI Endpoint.

Usage:
    python -m ml.deploy

Prerequisites:
    - Run ml/train.py first to generate ml/artifacts/model.joblib
    - Set BUCKET_NAME, ENDPOINT_ID (or leave ENDPOINT_ID blank to create new)
"""
import json
import logging
import os

from google.cloud import aiplatform, storage

# pyrefly: ignore [missing-import]
from src.core.config import (
    BUCKET_NAME,
    MODEL_DIR,
    PROJECT_ID,
    REGION,
    SERVING_CONTAINER_URI,
    SERVING_SKLEARN_MAJOR_MINOR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "model.joblib")
METADATA_PATH = os.path.join(ARTIFACTS_DIR, "model_metadata.json")


def _read_training_sklearn_version() -> str | None:
    if not os.path.exists(METADATA_PATH):
        return None
    with open(METADATA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh).get("sklearn_version")


def _validate_serving_compatibility() -> None:
    """Raises RuntimeError when the trained sklearn version mismatches the serving image."""
    trained = _read_training_sklearn_version()
    if not trained:
        logger.warning("model_metadata.json not found — skipping sklearn compatibility check.")
        return
    if not trained.startswith(f"{SERVING_SKLEARN_MAJOR_MINOR}."):
        raise RuntimeError(
            f"Incompatible artifact: trained with scikit-learn {trained}, "
            f"but serving image expects {SERVING_SKLEARN_MAJOR_MINOR}.x. "
            "Retrain with the correct scikit-learn version, then redeploy."
        )


def upload_to_gcs() -> str:
    """Uploads ml/artifacts/model.joblib (and metadata) to GCS. Returns the GCS directory URI."""
    logger.info("Uploading model artifact to GCS…")
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(BUCKET_NAME)

    bucket.blob(f"{MODEL_DIR}/model.joblib").upload_from_filename(MODEL_PATH)

    if os.path.exists(METADATA_PATH):
        bucket.blob(f"{MODEL_DIR}/model_metadata.json").upload_from_filename(METADATA_PATH)

    gcs_uri = f"gs://{BUCKET_NAME}/{MODEL_DIR}"
    logger.info("Uploaded → %s", gcs_uri)
    return gcs_uri


def deploy_to_vertex(gcs_model_uri: str) -> None:
    """Registers the model in Vertex AI Model Registry and deploys to an Endpoint."""
    logger.info("Initialising Vertex AI…")
    aiplatform.init(project=PROJECT_ID, location=REGION)

    _validate_serving_compatibility()

    logger.info("Registering model in Vertex AI Model Registry…")
    model = aiplatform.Model.upload(
        display_name="iot-anomaly-model",
        artifact_uri=gcs_model_uri,
        serving_container_image_uri=SERVING_CONTAINER_URI,
    )
    # pyrefly: ignore [missing-attribute]
    logger.info("Model registered: %s", model.resource_name)

    logger.info("Deploying to Endpoint (this takes ~5–10 min)…")
    # pyrefly: ignore [missing-attribute]
    endpoint = model.deploy(
        machine_type="n1-standard-2",
        min_replica_count=1,
        max_replica_count=1,
        sync=True,
    )
    logger.info("Deployment complete. Endpoint: %s", endpoint.resource_name)


def main() -> None:
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}. Run ml/train.py first.")
    gcs_uri = upload_to_gcs()
    deploy_to_vertex(gcs_uri)


if __name__ == "__main__":
    main()
