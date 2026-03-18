# Plan: AI Repo Plan

TL;DR - Подготовить минимально рабочую структуру для проекта на Python с контейнеризацией (Docker), тестами и CI, чтобы можно было локально собирать, тестировать и разворачивать сервисы.

## Steps

1. Инициализация проекта: создать базовую структуру директорий и манифесты для Python (*depends on nothing*).
2. Контейнеризация: добавить `Dockerfile`(ы) и `docker-compose.yml` для локального стека (*depends on step 1*).
3. Каркас сервисов: создать skeleton для backend (Python) компонентов, простое API и stub-агенты (*depends on step 1, parallel with step 2 for dev ergonomics*).
4. Интеграция очередей и LLM: подключить очередь (RabbitMQ) и LLM-адаптеры (stubs/реальные) (*depends on step 2 и 3*).
5. Тесты и CI: добавить unit/integration тесты и простую GitHub Actions workflow для lint+tests (*depends on step 3 и 4*).
6. Документация и релиз: обновить `README.md`, добавить инструкции dev-onboarding и релизного процесса (*depends on all previous*).

## Relevant files

- `README.md` — главная документация, расширить quickstart и архитектуру.
- `.github/copilot-instructions.md` — уже добавлен; расширить по мере роста репозитория.
- `pyproject.toml` — для управления зависимостями Python.
- `Dockerfile`, `docker-compose.yml` — контейнеризация и локальный стек.
- `backend/` или `src/` — код Python API и агентов.
- `.github/workflows/ci.yml` — CI для lint и тестов.

## Verification

1. Локальная сборка: `docker-compose build` и `docker-compose up` с запуском команд через Make — все сервисы стартуют.
2. Тесты: `pytest` для Python проходят локально в контейнерах.
3. CI: PR-triggered workflow выполняет lint и тесты.
4. Dev quickstart: новый разработчик может следовать `README.md` и поднять стек в 5–10 минут.

## Decisions / Assumptions

- Начнём с простых стубов для LLM (локальные адаптеры), заменяем на реальные провайдеры позже.
- Используем RabbitMQ как очередь по умолчанию (можно заменить на Redis/Redis Streams при необходимости).

## Further Considerations

1. CI secrets: хранить ключи и токены в секретах GitHub Actions, не в репозитории.
2. Разделение на монорепо/мульти-репо: по мере роста решить, выносить ли фронтенд в отдельный репозиторий.
