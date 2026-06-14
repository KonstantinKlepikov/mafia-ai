FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies and Ollama
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    netcat-traditional \
    ca-certificates \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama binary
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Verify Ollama installation
RUN ollama --version

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="/root/.local/bin:$PATH"

# Copy Poetry configuration
COPY pyproject.toml poetry.lock poetry.toml ./

# Install Python dependencies (without httpx and ollama Python SDK)
RUN POETRY_VIRTUALENVS_CREATE=false poetry install --no-root --no-interaction

# Copy source code
COPY src/shared ./shared
COPY src/services/mafia_service ./mafia_service
COPY config ./config

ENV PYTHONPATH=/app

EXPOSE 8550

# Copy entrypoint script
COPY infra/mafia_service/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
