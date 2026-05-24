from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query
from google.cloud import firestore

# pyrefly: ignore [missing-import]
from src.core.config import FIRESTORE_DATABASE, PROJECT_ID

router = APIRouter()

db = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)

_BUCKET_MINUTES: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "6h": 360,
    "1d": 1440,
}


@router.get("/anomaly-stats")
def get_anomaly_stats(hours: int = Query(default=24, ge=1, le=720)):
    """
    Returns KPI counts for Grafana stat/gauge panels.

    Query params:
      hours  — look-back window (default 24, max 720)

    Response:
      {
        "total": <int>,           # all-time count
        "window_hours": <int>,    # echoes the requested window
        "window_count": <int>     # anomalies within the window
      }
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    total_agg = db.collection("anomalies").count().get()
    total_count: int = total_agg[0][0].value

    window_agg = (
        db.collection("anomalies")
        .where(filter=firestore.FieldFilter("timestamp", ">=", cutoff))
        .count()
        .get()
    )
    window_count: int = window_agg[0][0].value

    return {
        "total": total_count,
        "window_hours": hours,
        "window_count": window_count,
    }


@router.get("/anomaly-trends")
def get_anomaly_trends(
    hours: int = Query(default=24, ge=1, le=720),
    bucket: Literal["5m", "15m", "1h", "6h", "1d"] = Query(default="1h"),
):
    """
    Returns time-bucketed anomaly counts for Grafana time-series panels.

    Query params:
      hours   — look-back window (default 24, max 720)
      bucket  — bucket size: 5m | 15m | 1h | 6h | 1d  (default 1h)

    Response:
      [ {"time": "<ISO8601>", "count": <int>}, ... ]
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    docs = (
        db.collection("anomalies")
        .where(filter=firestore.FieldFilter("timestamp", ">=", cutoff))
        .order_by("timestamp")
        .stream()
    )

    bucket_minutes = _BUCKET_MINUTES[bucket]
    counts: dict[datetime, int] = {}

    for doc in docs:
        data = doc.to_dict()
        ts = data.get("timestamp")
        if ts is None:
            continue
        # Firestore Timestamps are timezone-aware; plain datetimes are treated as UTC
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        # Floor timestamp to the nearest bucket boundary
        epoch_minutes = int(ts.timestamp()) // 60
        bucket_start_epoch = (epoch_minutes // bucket_minutes) * bucket_minutes
        bucket_dt = datetime.fromtimestamp(bucket_start_epoch * 60, tz=timezone.utc)
        counts[bucket_dt] = counts.get(bucket_dt, 0) + 1

    return [
        {"time": dt.isoformat(), "count": cnt}
        for dt, cnt in sorted(counts.items())
    ]
