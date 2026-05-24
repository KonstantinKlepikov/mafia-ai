#!/usr/bin/env bash
set -e

streamlit run \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    admin/app.py
