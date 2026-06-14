# Quick Start - Unified Mafia-AI Service

## Prerequisites

- Docker and Docker Compose
- (Optional) GPU with NVIDIA drivers for faster inference

## Configuration

Update `infra/.env` with your settings:

```bash
# Ollama settings
OLLAMA_MODEL=llama3.1:8b  # Or any model from ollama.ai/library
OLLAMA_TIMEOUT=120
LLM_POOL_SIZE=0  # 0 = auto-detect based on hardware

# Game settings
AGENT_COUNT=5
MAFIA_COUNT=2
PHASE_DURATION_SECONDS=30
VOTE_TIMEOUT_SECONDS=15
MESSAGE_MAX_TOKENS=150
VOTE_MAX_TOKENS=50
```

## Build and Run

```bash
cd infra
docker-compose up --build mafia-ai-service
```

**First run:** Will download the Ollama model (may take 5-10 minutes depending on model size).

**Subsequent runs:** Model is cached in `ollama_models` volume, starts quickly.

## Access the UI

Open your browser at: **http://localhost:38550**

## Usage

1. Click **"Start Game"** button
2. Agents will generate messages and vote
3. As Host, approve/reject/override votes
4. Use **"Ask Agent"** panel to query specific agents
5. Monitor game state in Status Panel

## Troubleshooting

### Container fails to start

Check logs:
```bash
docker-compose logs mafia-ai-service
```

Common issues:
- Ollama model download failed → Check internet connection
- Port 38550 already in use → Change `UI_PORT` in .env
- Out of memory → Use smaller model (e.g., `smollm2:135m`)

### Slow generation

Reduce model size or increase timeout:
```bash
OLLAMA_MODEL=smollm2:135m  # Smaller, faster model
OLLAMA_TIMEOUT=300  # Increase timeout to 5 minutes
```

### Check available models

```bash
docker exec mafia-ai-service ollama list
```

### Pull different model

```bash
docker exec mafia-ai-service ollama pull mistral
```

Then update `.env`:
```bash
OLLAMA_MODEL=mistral
```

And restart:
```bash
docker-compose restart mafia-ai-service
```

## Development

### Run without Docker

```bash
# Install ollama binary
curl -fsSL https://ollama.ai/install.sh | sh

# Pull model
ollama pull llama3.1:8b

# Install Python dependencies
poetry install

# Run
poetry run python -m src.services.mafia_service.main
```

### Run tests

```bash
poetry run pytest tests/unit/
poetry run pytest tests/integration/
```

## Architecture Overview

Single container with:
- **Flet UI** (port 8550) - Web interface
- **GameService** - Game orchestration, agent management
- **LLMService** - Inference coordinator
- **OllamaRunner** - Subprocess executor for `ollama run`
- **Ollama Binary** - Model inference engine

No HTTP between components → All in-process Python calls.

## Performance Tips

1. **GPU acceleration**: Ollama will auto-detect NVIDIA GPU
2. **Pool size**: Set `LLM_POOL_SIZE=4` for more parallelism (requires more RAM/VRAM)
3. **Model size**: Smaller models = faster generation but lower quality
4. **Agent count**: Start with 3-5 agents, increase gradually

## Cleanup

Stop and remove containers:
```bash
docker-compose down
```

Remove model cache (frees disk space):
```bash
docker-compose down -v
```

## Support

- See [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) for detailed architecture
- Check logs: `docker-compose logs -f mafia-ai-service`
- Open issue on GitHub (if available)
