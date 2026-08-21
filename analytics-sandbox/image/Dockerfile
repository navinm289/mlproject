# Base notebook image for the analytics sandbox.
#
# Phase 1 (now): plain JupyterLab + Python. This just pins the upstream image.
# You can deploy without building this at all (values.yaml points at the
# upstream image by default). Build + push to ECR only when you start adding
# libraries in Phase 2.
ARG BASE_TAG=python-3.11
FROM jupyter/base-notebook:${BASE_TAG}

# ---------------------------------------------------------------------------
# Phase 2 (later): add Python libraries.
#   Uncomment to install from requirements.txt, then bump the image tag in
#   helm/values.yaml (SINGLEUSER_IMAGE / SINGLEUSER_IMAGE_TAG).
# ---------------------------------------------------------------------------
# COPY requirements.txt /tmp/requirements.txt
# RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Phase 2/3 (later): Spark + lakehouse.
#   Option A: switch base to jupyter/pyspark-notebook.
#   Option B: add Spark + hadoop-aws + Iceberg runtime jars here, then wire
#   HMS Thrift URI + S3 warehouse via singleuser.extraEnv / spark-defaults.conf.
# ---------------------------------------------------------------------------
