import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# pyrefly: ignore [missing-import]
from src.api.routes.anomalies import router as anomalies_router
# pyrefly: ignore [missing-import]
from src.api.routes.metrics import router as metrics_router
# pyrefly: ignore [missing-import]
from src.api.routes.pubsub import router as pubsub_router
# pyrefly: ignore [missing-import]
from src.core.config import GEMINI_API_KEY, PROJECT_ID, REGION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# GCP environment wiring (must happen before any GCP client is instantiated)
# ---------------------------------------------------------------------------
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", REGION)
if GEMINI_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IoT AI Reliability API",
    description="Vertex ML + CrewAI anomaly detection backend",
    version="1.0.0",
)

# Allow Grafana Cloud (and any other client) to call the API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(anomalies_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(pubsub_router, prefix="/pubsub")

# Serve the static frontend
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_dashboard():
    """Serves the HTML dashboard."""
    dashboard_path = os.path.join(_STATIC_DIR, "index.html")
    with open(dashboard_path, "r", encoding="utf-8") as fh:
        return fh.read()
