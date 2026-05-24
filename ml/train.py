"""
Train an Isolation Forest model on historical BigQuery data and save the
artifact to ml/artifacts/.

Usage:
    python -m ml.train
"""
import json
import logging
import os

import joblib
import pandas as pd
import sklearn
from google.cloud import bigquery
from sklearn.ensemble import IsolationForest

# pyrefly: ignore [missing-import]
from src.core.config import DATASET_ID, PROJECT_ID, TABLE_ID, TRAINING_LOOKBACK_DAYS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "model.joblib")
METADATA_PATH = os.path.join(ARTIFACTS_DIR, "model_metadata.json")

bq_client = bigquery.Client(project=PROJECT_ID)


def fetch_training_data() -> pd.DataFrame:
    """Pulls the most recent sensor readings from BigQuery."""
    logger.info("Fetching historical data from BigQuery…")
    query = f"""
        SELECT timestamp, metric_value
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE metric_name = 'temperature'
          AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {TRAINING_LOOKBACK_DAYS} DAY)
        ORDER BY timestamp DESC
        LIMIT 10000
    """
    df = bq_client.query(query).to_dataframe()
    logger.info("Fetched %d rows.", len(df))
    return df


def train_model(df: pd.DataFrame) -> IsolationForest:
    """Trains an Isolation Forest on [metric_value, hour] features."""
    logger.info("Training Isolation Forest…")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour

    features = df[["metric_value", "hour"]]
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(features)
    logger.info("Training complete.")
    return model


def save_artifacts(model: IsolationForest) -> None:
    """Persists the model and training metadata to ml/artifacts/."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    joblib.dump(model, MODEL_PATH)
    logger.info("Model saved → %s", MODEL_PATH)

    metadata = {
        "sklearn_version": sklearn.__version__,
        "features": ["metric_value", "hour"],
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh)
    logger.info("Metadata saved → %s (sklearn %s)", METADATA_PATH, sklearn.__version__)


def smoke_test(model: IsolationForest) -> None:
    """Quick sanity check against known normal / anomalous values."""
    logger.info("Running smoke test…")
    test_df = pd.DataFrame({"metric_value": [50.0, 52.0, 95.0, 49.0], "hour": [14, 14, 14, 14]})
    predictions = model.predict(test_df)
    for val, pred in zip(test_df["metric_value"], predictions):
        status = "ANOMALY" if pred == -1 else "NORMAL"
        logger.info("  Reading %.1f → %s", val, status)


def main() -> None:
    df = fetch_training_data()
    if len(df) < 50:
        logger.warning("Not enough data (need ≥ 50 rows). Run the simulator longer.")
        return

    model = train_model(df)
    save_artifacts(model)
    smoke_test(model)


if __name__ == "__main__":
    main()
