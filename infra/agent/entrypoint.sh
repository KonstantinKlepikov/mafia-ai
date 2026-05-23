#! /usr/bin/env bash
set -e

uvicorn \
    --host 0.0.0.0 \
    --port "${AGENT_HTTP_PORT:-8100}" \
    agent.app:app
