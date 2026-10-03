# mafia-ai

AI-powered Mafia game with autonomous agents.

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────┐
│         Mafia-AI Service (Monolithic)                   │
│                                                         │
│   ┌──────────┐    ┌────────────────┐     ┌────────────┐ │
│   │  Flet UI │    │ FSM + Agents   │     │  Ollama    │ │
│   │ (Thread) │◀──▶│ (EventBus)     │────▶│ Subprocess │ │
│   └──────────┘    └────────────────┘     └────────────┘ │
│                          │                              │
│                          ▼                              │
│                   ┌──────────────┐                      │
│                   │  LLM         │                      │
│                   │ (Direct Call)│                      │
│                   └──────────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Build & Run

### Prerequisites

- Python 3.11+ (recommended: 3.14)
- Poetry for dependency management
- Docker & Docker Compose
- Ollama (for LLM inference)

### Setup

```bash
# Configure Python version (using pyenv)
echo "3.14.0" > .python-version

# Install dependencies
poetry install --with dev --no-root

# Configure virtual environment location
poetry config virtualenvs.in-project true
```

### Docker Services

```bash
# Build all Docker images
make build

# Start all services
make up

# Stop services
make down

# Run tests and linters
make check
```

### Service Management

```bash
# Restart service
docker compose -f infra/docker-compose.yml restart mafia-ai-service

# View logs
docker compose -f infra/docker-compose.yml logs -f mafia-ai-service

# Rebuild after code changes
make serve  # or: docker compose -f infra/docker-compose.yml up --build
```

## 🌐 Access Points

- **[Admin UI](http://localhost:38550)** — Flet web interface for game management

## 📊 Configuration

### Environment Variables

Key environment variables (see `infra/.env`):

```bash
# Ollama Settings
OLLAMA_MODEL=smollm2:135m

# Game Settings
PHASE_DURATION_SECONDS=60
VOTE_TIMEOUT_SECONDS=30
MESSAGE_MAX_TOKENS=150
VOTE_MAX_TOKENS=50
```

### Persona Configuration

Personas are defined in `config/prompts.yaml`:

```yaml
personas:
  persona-1:
    name: "Добродушная"
    persona_type: "good_natured"
    prompt: "Вы добрый и открытый человек..."
```

**10 personas included**: good_natured, hysteric, conspiracy_theorist, aristocrat, housewife, seductress, neurasthenic, clericalist, poetess, simpleton.

## 🛠️ Development

### Code Style

- **Formatter**: `ruff format`
- **Linter**: `ruff check --fix`
- **Line length**: 88 characters
- **Quotes**: Single quotes
- **Type hints**: Mandatory everywhere
- **Imports**: Sorted with `ruff` (I rule)

```bash
# Format code
poetry run ruff format src/ tests/

# Lint and auto-fix
poetry run ruff check --fix src/ tests/

# Type checking
poetry run mypy src/
```

### Pre-commit Checks

```bash
make check  # Runs pytest, mypy, ruff
```

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.

## 🔬 Research

Experimental code and design documents are in `research/`:
