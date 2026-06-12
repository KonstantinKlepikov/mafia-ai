# mafia-ai

AI-powered Mafia game with autonomous agents.

## 🏗️ Architecture

**Unified architecture**:

```text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Admin (Flet)   │────▶│  Orchestrator    │────▶│    LLM      │
│  Desktop UI     │ HTTP│  Game FSM        │ HTTP│   Pool      │
└─────────────────┘     └──────────────────┘     └─────────────┘
                               │                         │
                               │ HTTP                    │ HTTP
                               ▼                         ▼
                        ┌──────────────┐         ┌─────────────┐
                        │Unified Agent │         │   Ollama    │
                        │All AI agents │         │   Runtime   │
                        └──────────────┘         └─────────────┘
                               │
                               │ RabbitMQ (votes)
                               ▼
                        ┌──────────────┐
                        │  RabbitMQ    │
                        │  Messaging   │
                        └──────────────┘
```

### Core Services

- **Orchestrator** — Game state machine, coordinates phases (day/night), vote resolution
- **Unified Agent** — Single FastAPI service managing all AI agents
- **LLM Pool** — Parallel LLM inference with round-robin load balancing
- **Admin Flet** — Desktop UI for game control and monitoring
- **RabbitMQ** — Event bus for votes and game state updates
- **SQLite (in-memory)** — Persona storage and game state

### Key Changes from Old Architecture

**Before**: N agent containers + ChromaDB + Streamlit + Docker SDK management
**After**: 1 unified agent service + SQLite + Flet + REST API coordination

**Benefits**:

- ⚡ Faster agent initialization (no Docker container overhead)
- 🔄 Simplified message flow (HTTP calls instead of async RabbitMQ callbacks)
- 💾 Lighter dependencies (SQLite instead of ChromaDB)
- 🎯 Better resource utilization (LLM pool sharing across agents)
- 🧪 Easier testing (pure Python, no Docker mocking)

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
docker compose -f infra/docker-compose.yml restart mafia-ai-orchestrator
```

## 📁 Project Structure

```txt
mafia-ai/
├── config/
│   └── prompts.yaml           # Persona definitions (10 characters)
├── src/
│   ├── services/
│   │   ├── unified_agent/     # Single agent service (FastAPI)
│   │   ├── orchestrator/      # Game state machine
│   │   ├── llm/               # LLM pool manager
│   │   └── admin_flet/        # Desktop admin UI (Flet)
│   └── shared/
│       ├── models.py          # Pydantic models
│       ├── database.py        # SQLite async wrapper
│       ├── messaging.py       # RabbitMQ client
│       └── telemetry.py       # OpenTelemetry setup
├── tests/
│   └── unit/                  # Unit tests (83 tests)
└── infra/
    ├── docker-compose.yml     # Service definitions
    ├── unified_agent/         # Unified agent Dockerfile
    ├── orchestrator/          # Orchestrator Dockerfile
    ├── llm/                   # LLM service Dockerfile
    └── admin_flet/            # Admin Dockerfile
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

- **[Orchestrator API](http://localhost:38081)**:
    - `GET /game/state` — Current game state
    - `POST /game/start` — Start new game
    - `GET /game/agents` — List all agents
    - `POST /game/agents/{id}/question` — Ask agent a question
    - `POST /game/host/decision` — Submit host decision

- **[Unified Agent API](http://localhost:38082)**:
    - `POST /agents/{id}/init` — Initialize agent
    - `POST /agents/{id}/act` — Execute agent action
    - `GET /agents/{id}/state` — Get agent state
    - `DELETE /agents/{id}` — Eliminate agent
    - `GET /health` — Health check

- **[LLM Service](http://localhost:38080)**:
    - `POST /generate` — Generate LLM response
    - `GET /health` — Health check

### Monitoring & Observability

- **[RabbitMQ Management](http://localhost:35673)** (guest/guest)
- **[Zipkin Telemetry](http://localhost:29411)**
- **[Grafana Dashboards](http://localhost:33000)** (admin/admin)
    - Mafia-AI — Service Metrics
    - Mafia-AI — Log Analytics
- **[Prometheus](http://localhost:39090)**
- **[Admin-flet](http://localhost:38550)**

## 📊 Configuration

### Environment Variables

Key environment variables (see `infra/.env.example`):

```bash
# RabbitMQ
AMQP_URL=amqp://guest:guest@mafia-ai-rabbitmq:5672/

# LLM Settings
OLLAMA_URL=http://mafia-ai-ollama:11434
OLLAMA_MODEL=llama3.1:8b
LLM_POOL_SIZE=0  # 0 = auto-detect based on GPU/CPU

# Game Settings
AGENT_COUNT=10
MAFIA_COUNT=2
PHASE_DURATION_SECONDS=300
VOTE_TIMEOUT_SECONDS=60

# Telemetry
OTEL_SDK_DISABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://mafia-ai-otel-collector:4317
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

- `core-refactoring-plane.md` — Architectural refactoring plan
- `repo-plane.md` — Repository analysis
- `claude-plane.md` — AI agent design notes
