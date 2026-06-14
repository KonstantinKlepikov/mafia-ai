# mafia-ai

AI-powered Mafia game with autonomous agents.

## 🏗️ Architecture

**Monolithic architecture with embedded LLM**:

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
│                   │  LLMService  │                      │
│                   │ (Direct Call)│                      │
│                   └──────────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Core Components

- **Mafia-AI Service** — Single monolithic service with all functionality:
    - **FSM Engine** — Game state machine handling phases (day/night/voting)
    - **Agent Manager** — Embedded AI agents with direct async communication
    - **EventBus** — Internal pub/sub for UI synchronization (MESSAGE, VOTE, ANSWER, STATE_CHANGE events)
    - **Flet UI** — Integrated admin interface (port 8550, exposed as 38550)
    - **LLMService** — Direct in-process LLM inference management
    - **OllamaRunner** — Subprocess-based Ollama CLI execution with concurrency control
- **SQLite** — Persona storage with aiosqlite

### Key Architecture Principles

**Monolithic Design with Embedded LLM**:

- Single service with embedded UI, game logic, and LLM inference
- Ollama binary runs as subprocess, not separate container
- Direct Python imports instead of HTTP communication
- EventBus for internal event propagation
- Separate daemon thread for Flet UI (non-blocking)

**Benefits**:

- ⚡ Zero network overhead (direct method calls, no HTTP serialization)
- 🔄 Simplified deployment (single container, one Docker Compose service)
- 💾 Minimal dependencies (no httpx, fastapi, uvicorn, ollama SDK)
- 🎯 Better resource utilization (shared event loop, subprocess pool)
- 🧪 Easier testing (in-process communication, no mocking HTTP clients)
- 🚀 Lower latency (subprocess vs HTTP roundtrip)

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

## 📁 Project Structure

```txt
mafia-ai/
├── config/
│   └── prompts.yaml           # Persona definitions (10 characters)
├── src/
│   │
│   ├── core/
│   │    ├── event_bus.py       # Internal pub/sub
│   │    ├── service.py         # Game FSM + agents
│   │    ├── agent_logic.py     # Agent behavior
│   │    └── vote_resolver.py   # Voting logic
│   ├── llm/
│   │    ├── ollama_runner.py   # Subprocess execution
│   │    ├── service.py         # LLM facade
│   │    └── resource_detection.py  # GPU/CPU detection
│   ├── ui/
│   │    ├── main_app.py        # Flet application
│   │    ├── service_adapter.py # Direct method calls
│   │    └── event_adapter.py   # EventBus subscription
│   ├── shared/
│   │    ├── models.py          # Pydantic models
│   │    └── database.py        # SQLite async wrapper
│   ├── config.py      # MafiaServiceSettings
│   └── main.py        # Application entrypoint
├── tests/
│   └── unit/                  # Unit tests (71 tests)
└── infra/
    ├── docker-compose.yml     # Single service definition
    └── mafia_service/         # Unified service Dockerfile
        ├── Dockerfile
        └── entrypoint.sh      # Ollama model preload
```

## 🧪 Testing

```bash
# Run all unit tests (71 tests)
poetry run pytest tests/unit/ -v

# Run specific test file
poetry run pytest tests/unit/test_ollama_runner.py -v

# Run with coverage
poetry run pytest tests/unit/ --cov=src --cov-report=html
```

### Test Coverage

- `test_database.py` — 7 tests for SQLite operations
- `test_event_bus.py` — 15 tests for pub/sub system
- `test_game_service.py` — 36 tests for FSM and agent management
- `test_llm_service.py` — 9 tests for LLM schemas
- `test_ollama_runner.py` — 10 tests for subprocess execution and resource detection
- `test_shared_models.py` — 8 tests for Pydantic models
- `test_ui_adapters.py` — 10 tests for UI adapters

## 🌐 Access Points

- **Admin UI**: http://localhost:38550 — Flet web interface for game management

## 📊 Configuration

### Environment Variables

Key environment variables (see `infra/.env`):

```bash
# Ollama Settings
OLLAMA_MODEL=smollm2:135m
OLLAMA_BINARY_PATH=ollama
OLLAMA_TIMEOUT=120
LLM_POOL_SIZE=0  # 0 = auto-detect based on GPU/CPU

# Game Settings
AGENT_COUNT=10
MAFIA_COUNT=3
PHASE_DURATION_SECONDS=60
VOTE_TIMEOUT_SECONDS=30
MESSAGE_MAX_TOKENS=150
VOTE_MAX_TOKENS=50

# UI Settings
UI_ENABLED=true
UI_PORT=8550  # Exposed as 38550 externally
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
