<!-- Bootstrap copilot instructions for the repository -->
# Copilot / Agent Instructions

## Main python Guide

## Formatting & Style

- Follow PEP 8 as baseline
- Formatter/linter: `ruff`
- Line length: **88**
- Quote style: **single quotes**
- Encoding: UTF-8, no encoding declarations
- Import sorting: handled by `ruff check --fix` (rule `I`)

```toml
[tool.ruff]
line-length = 88

[tool.ruff.format]
quote-style = "single"

[tool.ruff.lint]
select = ["I"]
```

## Naming conventions

| Entity | Style | Example |
| --- | --- | --- |
| Module (file) | `snake_case` | `my_module.py` |
| Class | `CapitalCamelCase` | `FlightService` |
| Class with acronym | Acronym uppercase | `CapitalCamelCaseDSN` |
| Exception | `CapitalCamelCase` | `FlightNotFoundError` |
| Function / variable | `snake_case` | `get_flights` |
| Global constant | `CONSTANT_CASE` | `MAX_RETRY_COUNT` |
| Enum class | Singular noun | `FlightStatus`, `PointType` |
| Enum values | `snake_case` or `lowercase` | `'active'`, `'cancelled'` |

- Names must be ASCII English only
- Never use `l`, `O`, `I` as single-char name of variable, class, method or constant
- Prefix `_` = private (`_type`); suffix `_` = avoid keyword clash (`type_`)

## Type hints

Type hints are **mandatory everywhere** in production code, strongly recommended in tests

- Use built-in generic types: `list[str]`, `dict[str, int]`, `set[int]`, `tuple[str, ...]` and e.t.c
- Never use `List`, `Dict`, and other generic types from `typing` (deprecated since PEP 585)
- Use `X | None` instead of `Optional[X]`, use `X | Y` instead of `Union[X, Y]`
- Always annotate `-> None` for functions that return nothing
- Specify concrete inner types for generics: for example `dict[str, int]`or list[str], instead of bare `dict` or `list`
- Use alias names for complex types, for example `DataDict = dict[str, list[int]]`

```python
def process(items: list[str]) -> dict[str, int]:
    ...
```

## Code design

### Function

- Target ~20-30 lines per function body; >50 lines = decompose.
- One level of abstraction per function. Newer declare function insight gunction
- Never use `nonlocal` and `global`

### Classes design

- Never use `@staticmethod`

### Decorators

- Always use `@functools.wraps(func)` in decorator wrappers.
- If decorator may wrap both sync and async functions, provide both wrappers with `inspect.iscoroutinefunction` check

## Context managers

- Use `@contextmanager` from `contextlib` to define a factory function for `with` statement context managers

## Exceptions

- Create exception with name pattern: `<ExceptionName>Error(Exception)`
- All custom exceptions inherit cascading from the root exception of project
- Always use `from err` when re-raising: `raise ServiceError('msg') from err`
- Catch specific exceptions, not bare `Exception` (bare `except Exception` as last `except`)

```python
@contextmanager
def handle_router_errors():
    try:
        yield
    except ServiceNotFoundError as err:
        raise Http404Error(err)
    except ServiceValidationError as err:
        raise Http422Error(err)
    except Exception as err:
        raise Http500Error(err)
```

## if/else patterns

- Use early returns/raises to reduce nesting: check error conditions first.
- Avoid `else` after `return`/`raise` — use implicit else.
- For exhaustive checks over known values, always raise on unknown case instead of falling through.
- In loops, use `continue` for guard clauses to reduce nesting

```python
def get_item(self, item_id: int) -> Item:
    if item_id not in self.items:
        raise KeyError(f'Unknown item {item_id}')
    return self.items[item_id]

def get_label(status: str) -> str:
    if status == 'active':
        return 'Active'
    if status == 'cancelled':
        return 'Cancelled'
    raise ValueError(f'Unknown status: {status}')
```

## Documentation and comments

- Use english for all comments and doc strings
- Doc string style: **Google style** (`Args:`, or `Attrs:`, `Raises:`, `Yields:` and `Returns:`)
- No more than 88 symbol per line, include spaces
- Write complex doc strings in classes, methods and functions. Rarely use comments
- Comments must be complete sentences, starting with uppercase
- Always update comments and doc strings when changing code
- Newer use doc strings in the header of file

## Logging

- Use `loguru`
