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

- `make serve` not implemented
- `make down` not implemented
- `make check` tests, lint and mypy all

Use `infra` folder for difinition of docker images, related to development.

Use `research` folder for experiments and prompts.
