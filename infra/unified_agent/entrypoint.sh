#!/bin/sh
set -e

echo "Starting unified agent service..."

exec uvicorn unified_agent.app:app --host 0.0.0.0 --port 8100
