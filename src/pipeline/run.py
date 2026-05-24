"""
Dataflow pipeline entry point.

Run locally:
    python -m src.pipeline.run --runner DirectRunner

Run on Dataflow:
    python -m src.pipeline.run \
        --runner DataflowRunner \
        --project $PROJECT_ID \
        --region $REGION \
        --temp_location gs://$BUCKET_NAME/tmp \
        --requirements_file pipeline-requirements.txt
"""
import logging
import sys

import apache_beam as beam
import apache_beam.transforms.window as window
from apache_beam.options.pipeline_options import (
    PipelineOptions,
    SetupOptions,
    StandardOptions,
)

# pyrefly: ignore [missing-import]
from src.core.config import INPUT_TOPIC, OUTPUT_TOPIC, WINDOW_SIZE, WINDOW_SLIDE
# pyrefly: ignore [missing-import]
from src.pipeline.transforms import DetectAnomalyML, ParseAndKey


def run(argv=None) -> None:
    options = PipelineOptions(argv)
    options.view_as(StandardOptions).streaming = True
    # pipeline-requirements.txt lists only the packages needed on Dataflow workers,
    # avoiding unrelated deps (crewai, fastapi, etc.).
    options.view_as(SetupOptions).requirements_file = "pipeline-requirements.txt"

    logging.info("Starting ML-powered Dataflow pipeline…")

    with beam.Pipeline(options=options) as p:
        (
            p
            | "ReadFromPubSub" >> beam.io.ReadFromPubSub(topic=INPUT_TOPIC)
            | "ParseAndKey" >> beam.ParDo(ParseAndKey())
            | "ApplySlidingWindow"
            >> beam.WindowInto(
                window.SlidingWindows(size=WINDOW_SIZE, period=WINDOW_SLIDE)
            )
            | "GroupByKey" >> beam.GroupByKey()
            | "DetectAnomalyML" >> beam.ParDo(DetectAnomalyML())
            | "WriteToPubSub" >> beam.io.WriteToPubSub(topic=OUTPUT_TOPIC)
        )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run(sys.argv[1:])
