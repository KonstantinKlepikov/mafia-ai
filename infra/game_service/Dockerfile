FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y git curl && \
    curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml poetry.lock poetry.toml ./
RUN POETRY_VIRTUALENVS_CREATE=false poetry install --no-root

COPY src/shared ./shared
COPY src/services/game_service ./game_service

ENV PYTHONPATH=/app

EXPOSE 8081

COPY infra/game_service/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
