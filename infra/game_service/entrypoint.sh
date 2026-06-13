#! /usr/bin/env bash
set -e

uvicorn \
    --host 0.0.0.0 \
    --port 8081 \
    game_service.app:app
