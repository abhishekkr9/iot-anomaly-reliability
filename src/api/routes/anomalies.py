from fastapi import APIRouter
from google.cloud import firestore

# pyrefly: ignore [missing-import]
from src.core.config import FIRESTORE_DATABASE, PROJECT_ID

router = APIRouter()

db = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)


@router.get("/anomalies")
def get_anomalies():
    """Returns the latest 20 anomaly reports from Firestore."""
    docs = (
        db.collection("anomalies")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )
    results = []
    for doc in docs:
        data = doc.to_dict()
        # pyrefly: ignore [missing-attribute]
        ts = data.get("timestamp")
        # pyrefly: ignore [unsupported-operation]
        data["timestamp"] = ts.isoformat() if ts else None
        results.append(data)
    return results
