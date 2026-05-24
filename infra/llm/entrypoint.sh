#! /usr/bin/env bash
set -e

uvicorn \
    --reload \
    --host 0.0.0.0 \
    --port 8080 \
    "${SERVICENAME}".app:app

# gunicorn "${SERVICENAME}".app:app -k \
#     uvicorn.workers.UvicornWorker -b \
#     0.0.0.0:8080 \
#     --workers 3 \
#     --timeout 3600 \
#     --threads 10
