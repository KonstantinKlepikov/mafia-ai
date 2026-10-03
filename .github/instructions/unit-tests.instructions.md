---
name: 'Python Standards for unit tests'
description: 'Coding conventions for Python unit tests files'
applyTo: 'tests/init/*.py'
---

- Framework: **pytest** with `pytest-asyncio`
- Use test classes for groups of tests, that wraps similar tests (e.g. tests for one function or one method of class)
- One case - one test. Never combine many test cases in one test
- Naming: `test_<what>_<scenario>` (e.g. `test_create_flight_raises_on_duplicate_callsign`)
- Start any doc strings of tests with word `Test` (e.g. `"""Test function_name success with raw data"""`)
- Add doc strings to test classes
- Use fixtures in `conftest.py` at appropriate level; use factory fixtures for varied object creation
- Use `from _pytest.monkeypatch import MonkeyPatch` for mock functions
- Use `from types import MethodType` for mock class methods
- Start name of mock function with word `mock_` (e.g. `async def mock_some(*args, **kwargs)`)
- Mock any classes, functions and methods for test isolations
- Minimize doc strings in tests
- Use assert comments for clearly test fails (e.g. `assert this is that, f'wrong result: {this} not equal {that}'`)

```python
async def test_create_flight_with_valid_data(
    flight_service: FlightService,
    valid_flight_data: FlightCreate,
) -> None:
    """Terst create method with valid data success"""
    expected_callsign = valid_flight_data.callsign
    result = await flight_service.create(valid_flight_data)

    assert result.callsign == expected_callsign, (
        f'wrong {result.callsign}, expected {expected_callsign}'
    )
```