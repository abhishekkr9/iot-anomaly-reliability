# IoT AI Reliability System

Real-time IoT anomaly detection with automated investigation and dashboarding.

This project ingests telemetry, detects anomalies with an ML model, triggers an LLM-based root-cause summary, and exposes API endpoints for dashboards.

## Why This Exists

Industrial IoT systems generate high-volume sensor data. Teams usually face three issues:

- Too many false alerts mixed with normal variance.
- Slow incident triage and diagnosis.
- Low visibility across operations teams.

This system addresses those issues by combining stream processing, anomaly detection, AI investigation, and API-first observability.

## Service Translation (Cloud-Agnostic)

Use this table if you are familiar with general data/ML platforms but not Google Cloud.

| Capability (generic) | Used in this repo | Comparable concepts elsewhere |
|---|---|---|
| Event streaming / message bus | Cloud Pub/Sub topics (`telemetry-stream`, `anomaly-events`) | Apache Kafka topics, RabbitMQ exchanges |
| Stream processing engine | Apache Beam pipeline (`src/pipeline`) | Apache Flink, Spark Structured Streaming |
| Managed runner for Beam jobs | Cloud Dataflow | Self-managed Beam runner on Kubernetes/YARN |
| Online model inference endpoint | Vertex AI Endpoint | KFServing/KServe, SageMaker Endpoint |
| Object storage for model artifacts | Cloud Storage (GCS) | S3, Azure Blob, MinIO |
| Analytics warehouse for history/training | BigQuery | Snowflake, Redshift, Databricks SQL |
| Operational document store | Firestore | MongoDB, DynamoDB, Cosmos DB |
| Serverless API hosting | Cloud Run | Knative, AWS App Runner/Fargate, Azure Container Apps |
| Build pipeline | Cloud Build | GitHub Actions, GitLab CI, Jenkins |
| Dashboarding | Grafana Cloud | Self-hosted Grafana, Kibana (for visualization use cases) |
| LLM for investigation summaries | Gemini via CrewAI | OpenAI/Anthropic/local LLMs via CrewAI adapters |

Notes:
- Pub/Sub in this project plays the same role Kafka usually plays: decoupled producer-consumer messaging.
- Apache Beam is the programming model; Dataflow is the managed execution service for that Beam pipeline.

## High-Level Flow

1. Sensors (or simulator) publish telemetry events to input topic.
2. Beam pipeline windows events by sensor and performs anomaly scoring using deployed model.
3. Detected anomalies are published to output topic.
4. API receives anomaly push events and starts background investigation with CrewAI.
5. Investigation results are persisted and served to dashboards via API endpoints.

## Architecture

### System Overview

```mermaid
flowchart TB
  classDef source fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
  classDef stream fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
  classDef process fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
  classDef ml fill:#fce4ec,stroke:#c62828,stroke-width:2px,color:#b71c1c
  classDef api fill:#e0f2f1,stroke:#00695c,stroke-width:2px,color:#004d40
  classDef store fill:#fff8e1,stroke:#f9a825,stroke-width:2px,color:#f57f17
  classDef dash fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#4a148c

  S["🏭 IoT Sensors / Simulator\n(scripts/simulator.py)"]:::source

  T1["📨 Telemetry Topic\n(Pub/Sub · Kafka equivalent)"]:::stream

  BP["⚙️ Apache Beam Pipeline\n(Dataflow · Flink/Spark equivalent)\nSliding window → group by sensor"]:::process

  ML["🤖 Isolation Forest Endpoint\n(Vertex AI · SageMaker/KServe equivalent)"]:::ml

  T2["🚨 Anomaly Topic\n(Pub/Sub · Kafka equivalent)"]:::stream

  API["🌐 FastAPI Service\n(Cloud Run · Fargate/App Runner equivalent)"]:::api

  CREW["🕵️ CrewAI Investigator\n(Gemini LLM · any LLM via adapters)"]:::api

  BQ["📊 BigQuery\n(Snowflake/Redshift equivalent)\nSensor history for investigation"]:::store

  FS["📝 Firestore\n(MongoDB/DynamoDB equivalent)\nAI diagnostic reports"]:::store

  GF["📈 Grafana Cloud\nStat · Trend · Table panels"]:::dash

  S -- "raw telemetry JSON" --> T1
  T1 -- "windowed sensor groups" --> BP
  BP -- "feature vectors" --> ML
  ML -- "anomaly score = −1" --> T2
  T2 -- "push subscription" --> API
  API -- "background task" --> CREW
  CREW -- "SQL: last 5 readings" --> BQ
  CREW -- "write diagnostic report" --> FS
  API -- "GET /api/*" --> GF
```

### Request Lifecycle

```mermaid
sequenceDiagram
  participant S as Sensor
  participant PS as Pub/Sub Topic
  participant BM as Beam Pipeline
  participant VX as ML Endpoint
  participant AT as Anomaly Topic
  participant FA as FastAPI
  participant CR as CrewAI Agent
  participant BQ as BigQuery
  participant FS as Firestore
  participant GR as Grafana

  S->>PS: publish telemetry
  PS->>BM: deliver to sliding window
  BM->>VX: predict(features)
  VX-->>BM: anomaly_score
  BM->>AT: publish if score = −1
  AT->>FA: push subscription POST
  FA->>FA: queue background task
  FA-->>AT: 200 OK
  FA->>CR: investigate(anomaly)
  CR->>BQ: fetch sensor history
  BQ-->>CR: last 5 readings
  CR->>FS: save AI report
  GR->>FA: poll /api/anomalies
  FA->>FS: query reports
  FS-->>FA: results
  FA-->>GR: JSON response
```

## API Endpoints

- GET /api/anomalies
  - Returns latest investigated anomaly reports.
- GET /api/anomaly-stats?hours=24
  - Returns total and lookback-window counts.
- GET /api/anomaly-trends?hours=24&bucket=1h
  - Returns time-bucketed anomaly counts.
- POST /pubsub/anomaly-push
  - Push endpoint for anomaly events; queues background investigation.

## Project Structure

```text
.
|-- main.py
|-- Dockerfile
|-- Dockerfile.retrain
|-- cloudbuild.yaml
|-- requirements.txt
|-- pipeline-requirements.txt
|-- requirements-retrain.txt
|-- ml/
|   |-- train.py
|   |-- deploy.py
|   |-- retrain.py
|   `-- artifacts/
|-- scripts/
|   `-- simulator.py
|-- src/
|   |-- api/
|   |   |-- app.py
|   |   `-- routes/
|   |-- agents/
|   |   `-- investigator.py
|   |-- pipeline/
|   |   |-- run.py
|   |   `-- transforms.py
|   `-- core/
|       `-- config.py
`-- static/
    `-- index.html
```

## Quick Start

1. Create environment file

- Copy `.env.example` to `.env` and fill required values.

2. Install API dependencies

- pip install -r requirements.txt

3. Train model artifact

- python -m ml.train

4. Deploy model to inference endpoint

- python -m ml.deploy

5. Run streaming pipeline

- Local runner:
  - python -m src.pipeline.run --runner DirectRunner
- Managed Dataflow runner:
  - python -m src.pipeline.run --runner DataflowRunner --project $PROJECT_ID --region $REGION --temp_location gs://$BUCKET_NAME/tmp --requirements_file pipeline-requirements.txt

6. Start API service locally

- uvicorn main:app --host 0.0.0.0 --port 8080

7. Optional: run simulator

- python -m scripts.simulator

## Cloud Run Deployment

Build and deploy the API container:

- Build image:
  - gcloud builds submit --tag gcr.io/$PROJECT_ID/iot-api
- Deploy service:
  - gcloud run deploy iot-api --image gcr.io/$PROJECT_ID/iot-api --region $REGION --platform managed --allow-unauthenticated

The Docker image uses the root `Dockerfile` and serves FastAPI on `$PORT` (default 8080).

## Retraining Job

Manual run:

- python -m ml.retrain

Build retrainer image with Cloud Build config:

- gcloud builds submit --config cloudbuild.yaml .

Typical scheduler options:

- Cloud Scheduler triggering Cloud Run Job or HTTP endpoint.
- Cloud Tasks for queued/asynchronous invocation patterns.

