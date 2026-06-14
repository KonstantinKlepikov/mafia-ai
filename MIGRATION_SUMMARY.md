# Migration to Monolithic Service - Summary

## Изменения

Успешно объединены три микросервиса (ollama, llm, game_service) в единый монолитный сервис `mafia_service`.

## Ключевые изменения

### Архитектура

**До:**
```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Game Service   │─HTTP─│   LLM Service   │─HTTP─│  Ollama Server  │
│  (port 38550)   │      │  (port 38080)   │      │  (port 31434)   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

**После:**
```
┌───────────────────────────────────────┐
│     Unified Mafia Service             │
│  ┌───────────┐  ┌──────────────────┐ │
│  │ Flet UI   │  │ GameService      │ │
│  └───────────┘  │  ├─ AgentLogic   │ │
│                 │  └─ EventBus     │ │
│                 ├──────────────────┤ │
│                 │ LLMService       │ │
│                 │  └─ OllamaRunner │ │
│                 ├──────────────────┤ │
│                 │ Ollama Binary    │ │
│                 │  (subprocess)    │ │
│                 └──────────────────┘ │
│           (port 38550)                │
└───────────────────────────────────────┘
```

### Основные компоненты

1. **OllamaRunner** (`src/services/mafia_service/llm/ollama_runner.py`)
   - Заменяет HTTP-based ModelPool
   - Использует `subprocess.run()` для вызова `ollama run`
   - Асинхронная обертка через `asyncio.to_thread()`
   - Семафор для ограничения параллелизма

2. **LLMService** (`src/services/mafia_service/llm/service.py`)
   - Адаптирован для использования OllamaRunner
   - Сохранен интерфейс `generate(GenerateRequest)`
   - Автоматическое определение pool_size на основе hardware

3. **AgentLogic** (`src/services/mafia_service/core/agent_logic.py`)
   - Убрана зависимость от `httpx.AsyncClient`
   - Прямой вызов `LLMService.generate()`
   - Использует `GenerateRequest` вместо HTTP payload

4. **GameService** (`src/services/mafia_service/core/service.py`)
   - Принимает `LLMService` в конструкторе
   - Убрана зависимость от `llm_url`

5. **MafiaAdminApp** (`src/services/mafia_service/ui/main_app.py`)
   - Создает `LLMService` при старте
   - Передает его в `GameService`
   - Останавливает оба сервиса при завершении

### Dockerfile изменения

**Новый Dockerfile** (`infra/mafia_service/Dockerfile`):
- Base image: `python:3.14-slim`
- Установка Ollama binary через `curl -fsSL https://ollama.ai/install.sh | sh`
- Удалены зависимости: `httpx`, `ollama` Python SDK, `fastapi`, `uvicorn`
- Единая копия кода: `src/shared` + `src/services/mafia_service`
- Volume для кеширования моделей: `/root/.ollama`

**Entrypoint** (`infra/mafia_service/entrypoint.sh`):
- Проверка наличия модели: `ollama list | grep <model>`
- Автоматическая загрузка: `ollama pull <model>`
- Запуск приложения: `python -m mafia_service.main`

### Docker Compose

**Изменения:**
- Удалены сервисы: `mafia-ai-ollama`, `mafia-ai-llm`
- Единый сервис: `mafia-ai-service`
- Порт: `38550:8550` (только Flet UI)
- Volume: `ollama_models:/root/.ollama` (для кеширования моделей)
- Убраны `depends_on` и `networks` (не нужны)

**Новые переменные окружения:**
- `OLLAMA_BINARY_PATH` - путь к ollama binary (default: `ollama`)
- `OLLAMA_TIMEOUT` - таймаут subprocess в секундах (default: 120)

**Удаленные переменные:**
- `OLLAMA_URL` - больше не нужна (subprocess)
- `LLM_URL` - больше не нужна (прямой вызов)
- `LLM_QUEUE_MAX_SIZE` - устаревшая

### Зависимости Python

**Удалены из pyproject.toml:**
- `httpx` - HTTP клиент (заменен на subprocess)
- `ollama` - Ollama Python SDK (не нужен для subprocess)
- `fastapi` - Web framework (больше нет HTTP API)
- `uvicorn` - ASGI server (больше нет HTTP API)

**Оставлены:**
- `flet` - UI framework
- `aiosqlite` - Database
- `pydantic` - Config и schemas
- `loguru` - Logging
- `PyYAML` - Config loading

## Преимущества

1. **Простота развертывания**
   - Один контейнер вместо трех
   - Нет межсервисной коммуникации по HTTP
   - Меньше конфигурации и зависимостей

2. **Производительность**
   - Убран HTTP overhead (2 HTTP hop → прямой вызов)
   - Меньше сериализации/десериализации
   - Быстрее старт контейнера (один healthcheck)

3. **Надежность**
   - Меньше точек отказа
   - Нет проблем с сетевыми таймаутами между сервисами
   - Проще обработка ошибок (нет HTTP статусов)

4. **Разработка и отладка**
   - Все в одном процессе - проще debugging
   - Меньше конфигурационных файлов
   - Единая точка входа

## Дальнейшие шаги

### Запуск

```bash
cd infra
docker-compose up --build mafia-ai-service
```

### Проверка

1. **Логи контейнера** - должны показать успешную загрузку модели
2. **UI доступен** - http://localhost:38550
3. **Игра запускается** - кнопка "Start Game" → агенты генерируют сообщения

### Оптимизация (опционально)

Если производительность subprocess окажется недостаточной:
1. Можно вернуться к `ollama serve` + HTTP внутри контейнера
2. Запускать `ollama serve` в фоне в entrypoint.sh
3. Изменить OllamaRunner на HTTP клиент (локальный `http://localhost:11434`)

### Мониторинг

- **Latency subprocess**: измерить среднее время генерации сообщения
- **Concurrency**: проверить работу Semaphore при большом количестве агентов
- **Memory**: проверить использование памяти при длительной работе

## Структура проекта (после миграции)

```
src/services/
└── mafia_service/          # Единый монолитный сервис
    ├── __init__.py
    ├── main.py             # Entry point
    ├── config.py           # Unified settings
    ├── ui_config.py        # UI settings
    ├── core/               # Game logic
    │   ├── agent_logic.py  # Agent AI (без HTTP)
    │   ├── service.py      # GameService + AgentManager
    │   ├── event_bus.py
    │   └── vote_resolver.py
    ├── llm/                # LLM inference
    │   ├── service.py      # LLMService
    │   ├── ollama_runner.py # Subprocess executor
    │   ├── resource_detection.py
    │   └── schemas/
    │       └── llm_schemas.py
    └── ui/                 # Flet UI
        ├── main_app.py     # Main app (создает LLMService + GameService)
        ├── game_controls.py
        ├── message_feed.py
        ├── status_panel.py
        ├── ask_agent_panel.py
        ├── host_decision_panel.py
        ├── service_adapter.py
        └── event_adapter.py

infra/
└── mafia_service/
    ├── Dockerfile          # С установкой ollama binary
    └── entrypoint.sh       # Preload модели + запуск app
```

## Проблемы и решения

### Проблема 1: Ollama subprocess может быть медленным

**Решение:** Каждый `ollama run` создает новый процесс. Если это станет узким местом:
- Измерить латентность: добавить логирование времени выполнения
- Если >5s на генерацию - переключиться на `ollama serve` + HTTP внутри контейнера
- Использовать `asyncio.to_thread()` для неблокирующего выполнения

### Проблема 2: Concurrency ограничен

**Решение:** Semaphore ограничивает параллелизм. Для 10 агентов с pool_size=2:
- Максимум 2 одновременных генерации
- Остальные ждут в очереди
- Это нормально для CPU/GPU ограниченных систем
- Если нужно больше - увеличить `LLM_POOL_SIZE` в .env

### Проблема 3: OOM при загрузке модели

**Решение:** Модель загружается один раз в entrypoint.sh:
- Убедиться, что volume `ollama_models` смонтирован
- При перезапуске контейнера модель берется из volume (быстро)
- Первый запуск займет время (загрузка модели)

## Тестирование

### Unit тесты

Требуется создать тесты для `OllamaRunner`:
```python
# tests/unit/test_ollama_runner.py
async def test_ollama_runner_generate():
    runner = OllamaRunner('ollama', 'llama3.1:8b', 120, 2)
    request = GenerateRequest(
        system_prompt='You are helpful',
        messages=[MessageItem(role='user', content='Hello')],
        max_tokens=50
    )
    response = await runner.generate(request)
    assert isinstance(response, GenerateResponse)
    assert len(response.text) > 0
```

### Integration тесты

Проверить E2E сценарий:
1. Создать игру с 5 агентами
2. Запустить раунд
3. Проверить, что все агенты сгенерировали сообщения
4. Проверить голосование

## Откат (если нужно)

Если монолитный сервис не подходит:
1. `git revert` этого коммита
2. Вернуться к трем сервисам
3. Восстановить `httpx`, `ollama`, `fastapi` в pyproject.toml
4. `poetry install && poetry lock`
