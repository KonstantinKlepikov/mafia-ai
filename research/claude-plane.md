# Mafia-AI: Детальный поэтапный план разработки

> TL;DR — Реализовать игру «Мафия» с 10 AI-агентами (Mistral-6B / Ollama) в Docker-контейнерах.
> Агенты общаются через RabbitMQ, получают роли из игрового оркестратора,
> а человек-ведущий управляет игрой через Streamlit-панель.

---

## Фаза 1: Фундамент проекта

**Цель:** рабочая skeleton-структура репозитория, готовая к разработке.

### Шаг 1.1 — Структура директорий

Создать монорепо-структуру:

```txt
mafia-ai/
├── services/
│   ├── llm/          # Ollama + MCP-обёртка
│   ├── agent/        # образ одного агента
│   ├── orchestrator/ # игровой оркестратор
│   ├── admin/        # Streamlit-панель
│   └── vectordb/     # инициализация векторной БД
├── shared/           # общие pydantic-модели, протоколы
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── rabbitmq/     # конфигурация exchanges/queues
├── research/
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml    # корневая конфигурация Poetry + workspace
├── .env.example
└── Makefile
```

В каждую из папок поместить файл .gitkeep

### Шаг 1.2 — Общие модели (`shared/`)

Определить Pydantic-модели, используемые всеми сервисами:

- `AgentRole` — enum `CITIZEN | MAFIA`
- `GamePhase` — enum `NIGHT | NIGHT_VOTE | DAY | DAY_VOTE | HOST_DECISION`
- `Message` — `{sender_id, content, phase, round, target_audience: ALL | MAFIA_ONLY}`
- `VoteEvent` — `{voter_id, target_id, phase, round}`
- `GameState` — `{round, phase, alive_agents, eliminated}`
- `AgentState` — `{agent_id, role, persona_id, message_history}`

### Шаг 1.3 — Makefile и .env.example

Цели: `make build`, `make up`, `make down`, `make test`, `make lint`.
`.env.example` — переменные: `OLLAMA_MODEL`, `RABBITMQ_URL`, `VECTOR_DB_URL`,
`PHASE_DURATION_SECONDS`, `AGENT_COUNT`, `MAFIA_COUNT`.

---

## Фаза 2: LLM-контейнер (Ollama + MCP API)

**Цель:** контейнер с Mistral-6B, предоставляющий MCP-совместимый API.

### Шаг 2.1 — Ollama-контейнер

- Базовый образ: `ollama/ollama`
- Entrypoint-скрипт: `ollama pull mistral` при первом запуске
- Healthcheck по `/api/tags`
- Volume для кэша модели: `ollama_data:/root/.ollama`

### Шаг 2.2 — MCP-обёртка (`services/llm/`)

FastAPI-сервис (Python) поверх Ollama REST API, реализующий MCP-протокол:

- `POST /mcp/generate` — инициализирует новый контекст, принимает
  `{system_prompt, messages[], max_tokens}`, возвращает `{text, usage}`
- `POST /mcp/reset` — сброс контекста (stateless через параметры запроса)
- Логика: каждый запрос генерации — отдельный вызов к Ollama `/api/generate`
  с переданным системным промптом + историей (stateless MCP)
- Rate-limiting: очередь запросов внутри сервиса (asyncio.Queue), чтобы
  не перегружать модель параллельными вызовами

### Шаг 2.3 — Проверка

`curl http://llm-service:8080/mcp/generate` из другого контейнера возвращает текст.

---

## Фаза 3: Векторная БД для системных промптов

**Цель:** хранить и извлекать системные промпты агентов (персонажи, манера речи).

### Шаг 3.1 — Выбор и запуск БД

Использовать **ChromaDB** (легковесная, Python-native):

- Контейнер: `chromadb/chroma`
- Persistent volume: `chroma_data:/chroma/chroma`
- HTTP-сервер на порту 8000

### Шаг 3.2 — Инициализация промптов (`services/vectordb/`)

Python-скрипт `seed_prompts.py`:

- 10 уникальных персон: имя, характер, манера речи, ограничения (только игровые темы)
- Хранить как документы в коллекции `agent_personas` с метаданными `{persona_id, name}`
- Запускается как `init`-контейнер в docker-compose при первом старте

### Шаг 3.3 — Клиент в `shared/`

`VectorDBClient` — обёртка над `chromadb.HttpClient`:

- `get_persona(persona_id) -> SystemPrompt`
- `list_personas() -> list[SystemPrompt]`

---

## Фаза 4: Брокер сообщений (RabbitMQ)

**Цель:** ролевая маршрутизация сообщений между агентами и игроком.

### Шаг 4.1 — Конфигурация RabbitMQ

Exchange: `game_events` (тип: `topic`)
Routing key схема:

- `message.all` — всем (день, голосование)
- `message.mafia` — только мафии (ночь)
- `vote.*` — результаты голосований
- `game.state` — смена фаз от оркестратора

Очереди (создаются автоматически при подключении через `aio_pika`):

- Каждый агент: bind `message.all` + (если мафия) `message.mafia`
- Admin-панель: bind все routing keys
- Оркестратор: bind `vote.*` для сбора голосов

Конфигурация через `rabbitmq.conf` + `definitions.json` в `infra/rabbitmq/`.

### Шаг 4.2 — Shared messaging client

`MessagingClient` в `shared/messaging.py`:

- `publish(routing_key, payload: Message | VoteEvent)`
- `subscribe(routing_key_pattern, callback)` — async
- Использует `aio_pika`

---

## Фаза 5: Агент-сервис

**Цель:** один Docker-образ, параметризуемый через env-переменные, реализующий полный цикл агента.

### Шаг 5.1 — Конфигурация агента

Env-переменные образа: `AGENT_ID`, `PERSONA_ID`.
Роль (`MAFIA | CITIZEN`) агент получает от оркестратора в начале игры через RabbitMQ.

### Шаг 5.2 — Состояние агента (в памяти)

`AgentState`: роль, системный промпт, список полученных сообщений текущей игры.
Персона загружается из VectorDB при старте.

### Шаг 5.3 — Логика генерации сообщения

При получении сигнала от оркестратора «твоя очередь говорить»:

1. Сформировать контекст: системный промпт + история сообщений
2. Отправить в `LLM MCP API` (`POST /mcp/generate`)
3. Опубликовать ответ в RabbitMQ (`message.all` или `message.mafia`)
4. Добавить своё сообщение в локальную историю

### Шаг 5.4 — Логика голосования

- Ночное голосование (мафия): генерировать имя жертвы через LLM
- Дневное голосование (все): генерировать имя подозреваемого через LLM
- Публиковать `VoteEvent` в `vote.night` / `vote.day`

### Шаг 5.5 — Подписки агента

Слушать:

- `game.state` — получить роль, отреагировать на смену фазы / выбывание
- `message.all` (все фазы) — добавлять в историю
- `message.mafia` (только мафиози) — добавлять в историю
- `game.turn.{agent_id}` — сигнал «твоя очередь»

### Шаг 5.6 — Dockerfile агента

- Базовый образ: `python:3.12-slim`
- Poetry-зависимости: `shared`, `aio_pika`, `httpx`, `chromadb-client`
- `CMD ["python", "-m", "agent.main"]`

---

## Фаза 6: Игровой оркестратор

**Цель:** управлять игровым циклом, фазами, таймерами, голосованием.

### Шаг 6.1 — Инициализация игры

- Назначить роли 10 агентам (случайно: 7 горожан, 3 мафиози)
- Назначить персоны (persona_id) из VectorDB
- Опубликовать `game.state` с ролью каждого агента (каждый агент получает только свою роль)
- Использовать персональные routing keys: `game.init.{agent_id}`

### Шаг 6.2 — Игровой цикл (конечный автомат)

Состояния: `NIGHT → NIGHT_VOTE → RESOLVE_NIGHT → DAY → DAY_VOTE → HOST_DECISION → next NIGHT | GAME_OVER`

Реализация через `asyncio` + таймеры:

- NIGHT: запустить таймер (`PHASE_DURATION_SECONDS`), по очереди посылать `game.turn.{agent_id}` мафиозным агентам
- NIGHT_VOTE: запросить голос у каждого мафиози, ждать `VoteEvent` или таймаут
- RESOLVE_NIGHT: подсчитать голоса, если консенсус — выбить агента, опубликовать `game.state` с обновлённым списком живых
- DAY: аналогично NIGHT, но для всех живых агентов
- DAY_VOTE: собрать голоса от всех живых
- HOST_DECISION: опубликовать результаты, ждать решения ведущего (через RabbitMQ `host.decision`)
- Проверить условия победы: все мафиози выбыли → победа горожан; горожан ≤ мафии → победа мафии

### Шаг 6.3 — Обработка выбывания

- Удалить агента из списка живых
- Опубликовать `game.state.eliminated.{agent_id}` — агент прекращает участие

### Шаг 6.4 — REST API оркестратора

FastAPI:

- `POST /game/start` — запуск новой игры
- `GET /game/state` — текущее состояние игры (фаза, раунд, живые)
- `POST /game/host/decision` — решение ведущего (одобрить/отклонить/выбрать победителя)
- `GET /game/messages` — история сообщений текущей игры (SSE для стриминга)

---

## Фаза 7: Admin-панель (Streamlit)

**Цель:** интерфейс ведущего — наблюдение за игрой и принятие решений.

### Шаг 7.1 — Лента сообщений

- Подписаться на `message.*` через RabbitMQ (в фоновом потоке)
- Отображать сообщения в реальном времени с именем агента, фазой, раундом
- Ночные сообщения мафии — видны ведущему со специальной пометкой 🌙

### Шаг 7.2 — Статусная панель

- Текущая фаза, номер раунда
- Таблица агентов: имя, роль (открыта для ведущего), статус (жив/выбыл)
- Прогресс-бар оставшегося времени фазы

### Шаг 7.3 — Интерфейс голосования

- По завершении `DAY_VOTE` — показать результаты голосования
- Кнопки: «Одобрить», «Отклонить», при ничьей — выпадающий список кандидатов
- Отправка решения: `POST /game/host/decision`

### Шаг 7.4 — Управление игрой

- «Начать новую игру» → `POST /game/start`
- Лог событий (выбывания, смены фаз)

---

## Фаза 8: Docker Compose — полный стек

**Цель:** единая команда `docker-compose up` поднимает все сервисы.

### Шаг 8.1 — docker-compose.yml

Сервисы:

| Имя контейнера       | Образ / Dockerfile          | Порты       | Зависит от                |
|----------------------|-----------------------------|-------------|---------------------------|
| `ollama`             | `ollama/ollama`             | 11434       | —                         |
| `llm-service`        | `services/llm/Dockerfile`   | 8080        | ollama                    |
| `rabbitmq`           | `rabbitmq:3-management`     | 5672, 15672 | —                         |
| `chromadb`           | `chromadb/chroma`           | 8000        | —                         |
| `vectordb-seed`      | `services/vectordb/`        | —           | chromadb                  |
| `orchestrator`       | `services/orchestrator/`    | 8081        | llm, rabbit, chroma       |
| `agent-1`..`agent-10`| `services/agent/`           | —           | orchestrator, rabbit, llm |
| `admin`              | `services/admin/`           | 8501        | orchestrator              |

### Шаг 8.2 — Healthchecks и depends_on

Использовать `condition: service_healthy` для Ollama, RabbitMQ, ChromaDB.
`vectordb-seed` — тип `restart: on-failure`, завершается после инициализации.

### Шаг 8.3 — Сети и volumes

- Сеть: `game_net` (bridge) — все контейнеры
- Volumes: `ollama_data`, `chroma_data`, `rabbitmq_data`

---

## Фаза 9: Тесты и CI

### Шаг 9.1 — Unit-тесты (`tests/unit/`)

- `test_game_state.py` — логика оркестратора: назначение ролей, переходы фаз, подсчёт голосов
- `test_agent_logic.py` — формирование контекста LLM, обработка сообщений
- `test_messaging.py` — маршрутизация (mock RabbitMQ через `aio_pika` mocks)
- `test_vote_resolution.py` — все сценарии: консенсус, ничья, таймаут

### Шаг 9.2 — Integration-тесты (`tests/integration/`)

- Поднять `docker-compose.test.yml` (без Ollama, с mock LLM-сервисом)
- `test_full_game_round.py` — пройти один раунд: ночь → голосование → день → голосование → решение ведущего

### Шаг 9.3 — CI (GitHub Actions `.github/workflows/ci.yml`)

Триггеры: `push` и `pull_request` в `main`.
Jobs:

1. `lint` — `ruff check .` + `mypy`
2. `unit-tests` — `pytest tests/unit/` в Python-окружении
3. `integration-tests` — запуск `docker-compose.test.yml`, выполнение `pytest tests/integration/`

---

## Зависимости между фазами

```txt
Фаза 1 (Фундамент)
  └─> Фаза 2 (LLM) ──────────────┐
  └─> Фаза 3 (VectorDB) ─────────┤
  └─> Фаза 4 (RabbitMQ) ─────────┤
                                 ▼
                          Фаза 5 (Агент) ───────┐
                          Фаза 6 (Оркестратор) ─┐
                                                ▼
                                         Фаза 7 (Admin)
                                         Фаза 8 (Compose)
                                         Фаза 9 (Тесты + CI)
```

Фазы 2, 3, 4 — **параллельны** между собой.
Фазы 5 и 6 — **параллельны**, начинаются после 2–4.

---

## Верификация по этапам

| Фаза | Проверка                                                                 |
|------|--------------------------------------------------------------------------|
| 1    | `make lint` проходит, структура директорий создана                       |
| 2    | `curl http://localhost:8080/mcp/generate` возвращает текст от Mistral    |
| 3    | seed-скрипт записывает 10 персон, `get_persona()` возвращает промпт      |
| 4    | RabbitMQ management UI показывает exchanges и очереди                    |
| 5    | Один агент генерирует сообщение и публикует его в RabbitMQ               |
| 6    | Оркестратор проходит полный цикл раунда с заглушками агентов             |
| 7    | Streamlit-панель отображает сообщения и позволяет одобрить голосование   |
| 8    | `make up` поднимает весь стек, игра запускается автоматически            |
| 9    | `pytest` + CI зелёный на всех jobs                                       |

---

## Ключевые технические решения

- **Stateless LLM**: каждый вызов MCP API передаёт полный контекст — сброс контекста модели не нужен между агентами
- **Порядок высказываний**: оркестратор последовательно шлёт `game.turn.{id}`, ждёт подтверждения публикации → агенты не «перебивают» друг друга; таймаут не дожидается зависшего агента
- **Ролевая маршрутизация**: routing key `message.mafia` виден только подписанным мафиозным агентам и admin-панели; горожане физически не получают ночные сообщения
- **Персоны в VectorDB**: при масштабировании (>10 агентов) семантический поиск позволит подбирать подходящую персону; сейчас выбор детерминирован по `persona_id`

---

## Явно вне скоупа

- Веб-интерфейс с аутентификацией (достаточно Streamlit без auth)
- Мультиигровой режим (несколько параллельных игр)
- Сохранение истории игр в реляционной БД
- Замена Mistral на другую модель (оставить как настраиваемый параметр `OLLAMA_MODEL`)

---

**Краткое резюме плана:**

- **9 фаз**, из которых фазы 2–4 (LLM, VectorDB, RabbitMQ) идут **параллельно**
- **Ключевые архитектурные решения**: stateless MCP для LLM, topic exchange в RabbitMQ для ролевой маршрутизации, оркестратор-автомат, последовательные «ходы» агентов через `game.turn.{id}`
- **Стек**: Ollama + Mistral-6B, ChromaDB, RabbitMQ, FastAPI (x2: llm-service + orchestrator), Streamlit, Poetry, pytest, GitHub Actions
