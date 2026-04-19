COMPOSE_FILE := infra/docker-compose.yml
ENV_FILE     := .env

# target: all - Default target.
all: help

# target: help - List of available targets.
help:
	@egrep "^# target:" [Mm]akefile

# target: build - Build all Docker images defined in docker-compose.yml.
build:
	@docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) build

# target: up - Start all services in detached mode.
up:
	@docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d

# target: serve - run docker-compose
serve:
	@sh ./scripts/up-dev.sh

# target: down - Stop and remove all containers, networks.
down:
	@docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) down

# target: check - Run tests, mypy and flake8.
check:
	@pytest; mypy src; mypy tests; flake8 src; flake8 tests