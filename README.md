# mafia-ai

AI-powered Mafia game with autonomous agents.

## 🏗️ Architecture

**Integrated architecture**:

```text
┌─────────────────────────────────────────┐     ┌─────────────┐
│     Game Service (Unified)              │     │    LLM      │
│   ┌──────────┐    ┌────────────────┐    │────▶│   Pool      │
│   │  Flet UI │    │ FSM + Agents   │    │ HTTP│             │
│   │ (Thread) │◀──▶│ (EventBus)     │    │     └─────────────┘
│   └──────────┘    └────────────────┘    │           │ HTTP
│                                         │           ▼
└─────────────────────────────────────────┘     ┌─────────────┐
                                                │   Ollama    │
                                                │   Runtime   │
                                                └─────────────┘
```

### Core Services

- **Game Service** — Unified service combining game orchestration, agent management, and admin UI:
    - **FSM Engine** — Game state machine handling phases (day/night/voting)
    - **Agent Manager** — Embedded AI agents with direct async communication
    - **EventBus** — Internal pub/sub for UI synchronization (MESSAGE, VOTE, ANSWER, STATE_CHANGE events)
    - **Flet UI** — Integrated admin interface running in daemon thread (port 8550)
    - **FastAPI** — REST API for external integrations (port 8081)
- **LLM Pool** — Parallel LLM inference with round-robin load balancing
- **SQLite (in-memory)** — Persona storage

### Key Architecture Principles

**Monolithic Design**:

- Single service with embedded UI and business logic
- Direct method calls instead of HTTP/RabbitMQ for UI communication
- EventBus for internal event propagation
- Separate daemon thread for Flet UI (non-blocking)

**Benefits**:

- ⚡ Zero network overhead for UI operations (direct method calls)
- 🔄 Simplified deployment (single container)
- 💾 Lighter dependencies (no separate UI service)
- 🎯 Better resource utilization (shared event loop)
- 🧪 Easier testing (in-process communication)

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

### Service Restart Example

```bash
docker compose -f infra/docker-compose.yml restart mafia-ai-game-service
```

### Access Points

- **Admin UI**: http://localhost:38550 (Flet web interface)

## 📁 Project Structure

```txt
mafia-ai/
├── config/
│   └── prompts.yaml           # Persona definitions (10 characters)
├── src/
│   ├── services/
│   │   ├── game_service/      # Unified game + UI service (FastAPI + Flet)
│   │   │   ├── core/
│   │   │   │   ├── event_bus.py       # Internal pub/sub
│   │   │   │   ├── service.py         # Game FSM + agents
│   │   │   │   └── agent_logic.py     # Agent behavior
│   │   │   ├── ui/
│   │   │   │   ├── service_adapter.py # Direct method calls
│   │   │   │   └── event_adapter.py   # EventBus subscription
│   │   │   └── main_app.py    # Integrated Flet UI
│   │   ├── llm/               # LLM pool manager
│   └── shared/
│       ├── models.py          # Pydantic models
│       └── database.py        # SQLite async wrapper
├── tests/
│   └── unit/                  # Unit tests (83 tests)
└── infra/
    ├── docker-compose.yml     # Service definitions
    ├── llm/                   # LLM service Dockerfile
    └── game_service/          # Admin Dockerfile
```

## 🧪 Testing

```bash
# Run all unit tests
poetry run pytest tests/unit/ -v

# Run specific test file
poetry run pytest tests/unit/test_database.py -v

# Run with coverage
poetry run pytest tests/unit/ --cov=src --cov-report=html
```

## 🌐 Endpoints

### Services

- **[LLM Service](http://localhost:38080)**:
- **[Admin-flet](http://localhost:38550)**

## 📊 Configuration

### Environment Variables

Key environment variables (see `infra/.env.example`):

```bash
# LLM Settings
OLLAMA_URL=http://mafia-ai-ollama:11434
OLLAMA_MODEL=llama3.1:8b
LLM_POOL_SIZE=0  # 0 = auto-detect based on GPU/CPU

# Game Settings
AGENT_COUNT=10
MAFIA_COUNT=2
PHASE_DURATION_SECONDS=300
VOTE_TIMEOUT_SECONDS=60
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
