FROM python:3.12-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Poetry
RUN apt-get update && apt-get install -y git curl && \
    curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files and install production dependencies only
COPY pyproject.toml poetry.lock poetry.toml ./
RUN POETRY_VIRTUALENVS_CREATE=false poetry install --with dev --no-root

# Copy shared models and the llm service source
COPY src/shared ./shared
COPY src/services/llm ./llm

ENV PYTHONPATH=/app

EXPOSE 8080

COPY infra/llm/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]