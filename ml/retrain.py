"""
Automated ML Retraining Job: Fetch fresh data, train model, and deploy to existing Vertex AI Endpoint.

Usage:
    python -m ml.retrain

This job is designed to run on a schedule (e.g., via Cloud Scheduler, Cloud Tasks, or cron).
It fetches the newest data from BigQuery, trains a fresh Isolation Forest model,
uploads it to Cloud Storage, and deploys to your existing Vertex AI Endpoint.

Prerequisites:
    - Set environment variables: PROJECT_ID, ENDPOINT_ID, BUCKET_NAME
    - Vertex AI Endpoint must already exist (ENDPOINT_ID points to an active endpoint)
    - BigQuery dataset and table must exist
"""
import json
import logging
import os
from datetime import datetime

import joblib
import pandas as pd
import sklearn
from google.cloud import aiplatform, bigquery, storage
from sklearn.ensemble import IsolationForest

# pyrefly: ignore [missing-import]
from src.core.config import (
    BUCKET_NAME,
    DATASET_ID,
    ENDPOINT_ID,
    PROJECT_ID,
    REGION,
    RETRAIN_GCS_MODEL_DIR,
    RETRAIN_MIN_ROWS,
    RETRAIN_MODEL_DISPLAY_NAME,
    RETRAIN_QUERY_LIMIT,
    SERVING_CONTAINER_URI,
    TABLE_ID,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
bq_client = bigquery.Client(project=PROJECT_ID)


def fetch_fresh_data(limit: int = RETRAIN_QUERY_LIMIT) -> pd.DataFrame:
    """
    Fetches the newest sensor readings from BigQuery.
    
    Args:
        limit: Maximum number of rows to fetch (default: RETRAIN_QUERY_LIMIT)
    
    Returns:
        DataFrame with columns: timestamp, metric_value
    """
    logger.info("📥 Fetching latest data from BigQuery (limit: %d)…", limit)
    query = f"""
        SELECT timestamp, metric_value
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE metric_name = 'temperature'
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    df = bq_client.query(query).to_dataframe()
    logger.info("✓ Fetched %d rows.", len(df))
    
    if len(df) < RETRAIN_MIN_ROWS:
        logger.warning("⚠️ Insufficient data (%d rows). Need at least %d rows. Aborting.", len(df), RETRAIN_MIN_ROWS)
        raise ValueError(f"Not enough data to retrain. Got {len(df)} rows, need {RETRAIN_MIN_ROWS}.")
    
    return df


def train_model(df: pd.DataFrame) -> IsolationForest:
    """
    Trains a fresh Isolation Forest model on [metric_value, hour] features.
    
    Args:
        df: DataFrame with timestamp and metric_value columns
    
    Returns:
        Trained IsolationForest model
    """
    logger.info("🧠 Training new Isolation Forest model…")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour

    features = df[["metric_value", "hour"]]
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(features)
    logger.info("✓ Training complete.")
    return model


def upload_model_to_gcs(model: IsolationForest) -> str:
    """
    Uploads the trained model artifact to Cloud Storage.
    
    Args:
        model: Trained IsolationForest model
    
    Returns:
        GCS URI (gs://bucket/path) of the uploaded model directory
    """
    logger.info("☁️ Uploading model to Cloud Storage…")
    
    # Create a temporary local directory for the model
    temp_model_path = os.path.join(ARTIFACTS_DIR, "model_retrain.joblib")
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    joblib.dump(model, temp_model_path)
    
    # Upload to GCS with timestamped versioning
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    gcs_path = f"{RETRAIN_GCS_MODEL_DIR}/v{timestamp}/model.joblib"
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(temp_model_path)
    
    # Also upload metadata
    metadata = {
        "sklearn_version": sklearn.__version__,
        "features": ["metric_value", "hour"],
        "trained_timestamp": datetime.now().isoformat(),
        "model_version": f"v{timestamp}",
    }
    metadata_path = os.path.join(ARTIFACTS_DIR, "model_metadata_retrain.json")
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh)
    
    metadata_blob = bucket.blob(f"{RETRAIN_GCS_MODEL_DIR}/v{timestamp}/model_metadata.json")
    metadata_blob.upload_from_filename(metadata_path)
    
    gcs_uri = f"gs://{BUCKET_NAME}/{RETRAIN_GCS_MODEL_DIR}/v{timestamp}"
    logger.info("✓ Uploaded → %s", gcs_uri)
    
    # Clean up temp files
    os.remove(temp_model_path)
    os.remove(metadata_path)
    
    return gcs_uri


def deploy_to_existing_endpoint(gcs_model_uri: str) -> None:
    """
    Registers the retrained model in Vertex AI and deploys it to the existing Endpoint.
    
    This function will update the existing Endpoint with the new model.
    Vertex AI will automatically route 100% of traffic to the updated model.
    
    Args:
        gcs_model_uri: GCS URI (gs://bucket/path) pointing to the model directory
    """
    logger.info("🔄 Deploying to Vertex AI Endpoint…")
    aiplatform.init(project=PROJECT_ID, location=REGION)
    
    # Register the model in Vertex AI Model Registry
    logger.info("Registering model in Vertex AI Model Registry…")
    try:
        new_model = aiplatform.Model.upload(
            display_name=RETRAIN_MODEL_DISPLAY_NAME,
            artifact_uri=gcs_model_uri,
            serving_container_image_uri=SERVING_CONTAINER_URI,
        )
        logger.info("✓ Model registered: %s", new_model.resource_name)
    except Exception as e:
        logger.error("Failed to register model: %s", e)
        raise
    
    # Get the existing endpoint
    logger.info("Connecting to existing Endpoint (ID: %s)…", ENDPOINT_ID)
    try:
        endpoint = aiplatform.Endpoint(ENDPOINT_ID)
        logger.info("✓ Endpoint found: %s", endpoint.resource_name)
    except Exception as e:
        logger.error("Failed to connect to Endpoint. Check ENDPOINT_ID: %s", ENDPOINT_ID)
        raise
    
    # Deploy the new model to the existing endpoint
    logger.info("Deploying new model to Endpoint (this takes ~5–10 min)…")
    try:
        new_model.deploy(
            endpoint=endpoint,
            machine_type="n1-standard-2",
            min_replica_count=1,
            max_replica_count=1,
            sync=True,
        )
        logger.info("🎉 SUCCESS! Model retrained and Endpoint updated seamlessly.")
    except Exception as e:
        logger.error("Deployment failed: %s", e)
        raise


def main() -> None:
    """Execute the complete automated retraining pipeline."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Automated ML Retraining Job…")
    logger.info("=" * 60)
    
    try:
        # 1. Fetch fresh data
        df = fetch_fresh_data()
        
        # 2. Train model
        model = train_model(df)
        
        # 3. Upload to GCS
        gcs_uri = upload_model_to_gcs(model)
        
        # 4. Deploy to existing Endpoint
        deploy_to_existing_endpoint(gcs_uri)
        
        logger.info("=" * 60)
        logger.info("✅ Retraining job completed successfully!")
        logger.info("=" * 60)
        
    except ValueError as e:
        logger.error("Validation error: %s", e)
        return
    except Exception as e:
        logger.error("Retraining job failed: %s", e)
        raise


if __name__ == "__main__":
    main()
