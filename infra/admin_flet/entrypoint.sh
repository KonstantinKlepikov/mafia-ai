#!/bin/sh
set -e

echo "Starting admin flet service..."

exec python -m admin_flet.main
