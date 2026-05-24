import base64
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

# pyrefly: ignore [missing-import]
from src.agents.investigator import investigate_anomaly

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/anomaly-push")
async def receive_anomaly(request: Request, background_tasks: BackgroundTasks):
    """Pub/Sub push subscription endpoint — decodes the message and queues an AI investigation."""
    try:
        body = await request.json()
        message = body.get("message", {})

        encoded_data = message.get("data", "")
        if not encoded_data:
            return {"status": "ignored", "reason": "No data in message"}

        decoded_data = base64.b64decode(encoded_data).decode("utf-8")
        anomaly_payload = json.loads(decoded_data)

        logger.info("[PubSub] Received anomaly: %s", anomaly_payload)

        background_tasks.add_task(investigate_anomaly, anomaly_payload)
        return {"status": "success", "message": "Anomaly queued for AI investigation."}

    except Exception as exc:
        logger.exception("[PubSub] Failed to process message: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process Pub/Sub message")
