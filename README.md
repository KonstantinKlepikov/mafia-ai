# mafia-ai

## Build local

Change python version before instalation (install and use pyenv for different python versions)

```python
# .python-version

3.14.0
```

Define placement of .venv folder local

```python
# poetry.toml

virtualenvs.create = true
virtualenvs.prefer-active-python = true
# ... some other variables
```

- `poetry config virtualenvs.in-project true` if you don't use poetry.toml
- `poetry install --with dev --no-root` install poetry dependencies

Use local

- `make build` — build all Docker images defined in `infra/docker-compose.yml`
- `make up` — start all services in detached mode
- `make down` — stop and remove all containers and networks
- `make check` — run tests, mypy and flake8

Use `infra` folder for difinition of docker images, related to development.

Use `research` folder for experiments and prompts.

Endpoints

- [rq-ui](http://localhost:35673)
- [llm/docs](http://localhost:38080/docs)
- [chroma-db](http://localhost:36333)
- [zipkin telemetry](http://localhost:29411)
