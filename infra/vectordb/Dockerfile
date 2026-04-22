FROM python:3.14-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps and Poetry
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/* && \
    curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files and install dependencies
COPY pyproject.toml poetry.lock poetry.toml ./
RUN POETRY_VIRTUALENVS_CREATE=false poetry install --no-root

# Copy seed script
COPY src/services/vectordb ./src/services/vectordb

ENV PYTHONPATH=/app

CMD ["python", "src/services/vectordb/seed_prompts.py"]
