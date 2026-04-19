#! /usr/bin/env sh

# Exit in case of error
set -e

docker compose \
-f ./infra//docker-compose.yml \
config > docker-stack.yml

docker compose -f docker-stack.yml build
docker compose -f docker-stack.yml down --remove-orphans
docker compose -f docker-stack.yml up -d