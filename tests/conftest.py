import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from utils import make_persona

from services.agent.app import get_agent_info
from services.agent.config import AgentSettings
from services.agent.core.service import AgentService
from services.orchestrator.app import app as _orch_app
from shared.models import AgentInfo, GamePhase, GameState, Message, PersonaType


os.environ.setdefault('AGENT_ID', '_test_agent_')
os.environ.setdefault('PERSONA_ID', '_test_persona_')


@pytest.fixture(scope='session')
def settings() -> AgentSettings:
    """Default AgentSettings for unit tests."""
    return AgentSettings(
        agent_id='agent-1',
        persona_id='persona_1_good_natured',
        amqp_url='amqp://guest:guest@localhost/',
        llm_url='http://localhost:8080',
        vectordb_host='localhost',
        vectordb_port=8000,
    )


@pytest.fixture(scope='session')
def agent_service(settings: AgentSettings) -> AgentService:
    """Default AgentSettings for unit tests."""
    return AgentService(settings)


@pytest.fixture(scope='session')
def agent_service_with_persona(settings: AgentSettings) -> AgentService:
    """AgentService with pre-loaded persona for session-scoped usage."""
    service = AgentService(settings=settings)
    service._AgentService__persona = make_persona(  # type: ignore[attr-defined]
        name='persona_1_good_natured',
        _id='uuid-test',
        _type=PersonaType.GOOD_NATURED,
        prompt='You are a kind-hearted villager.',
    )
    return service


@pytest.fixture
def service_with_persona(settings: AgentSettings) -> AgentService:
    """Fresh AgentService with pre-loaded persona per test function."""
    service = AgentService(settings=settings)
    service._AgentService__persona = make_persona(  # type: ignore[attr-defined]
        name='persona_1_good_natured',
        _id='uuid-test',
        _type=PersonaType.GOOD_NATURED,
        prompt='You are a kind-hearted villager.',
    )
    return service


@pytest.fixture(scope='session')
def agent_lifespam(agent_service: AgentService) -> Callable:
    """Lifespam to start agent service"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[dict[str, AgentService], None]:
        try:
            await agent_service.start()
        except Exception as exc:
            logger.error(f'AgentService failed to start: {exc}')
        logger.info(f'Agent {agent_service._settings.agent_id} HTTP server ready')
        try:
            yield {'service': agent_service}
        finally:
            await agent_service.stop()

    return lifespan


@pytest.fixture(scope='session')
def agent_app(agent_lifespam: Callable) -> FastAPI:
    """Override fastapi agent app"""
    test_app = FastAPI(
        title='Agent Service',
        description='Single Mafia-AI agent exposing its current state.',
        version='0.1.0',
        lifespan=agent_lifespam,
    )
    test_app.get('/agent/info', response_model=AgentInfo)(get_agent_info)
    return test_app


@pytest.fixture(scope='session')
def agent_client(agent_app: FastAPI) -> Generator[TestClient, None, None]:
    """Test client"""
    with TestClient(agent_app) as client:
        yield client


@pytest.fixture
def mock_orchestrator_svc() -> MagicMock:
    """Mocked OrchestratorService for orchestrator API tests."""
    svc = MagicMock()
    svc.begin_game = AsyncMock()
    svc.get_game_state = MagicMock(
        return_value=GameState(
            round=0,
            phase=GamePhase.DAY,
            alive_agents=[],
            eliminated=[],
        )
    )
    svc.submit_host_decision = MagicMock()
    svc.get_agents_info = AsyncMock(return_value={})
    svc.get_agent_info = AsyncMock(return_value=None)
    svc.ask_agent = AsyncMock()
    svc.get_agent_answer = AsyncMock(return_value=None)
    svc.force_stop_agent = AsyncMock()

    async def _subscribe() -> AsyncGenerator[Message, None]:
        return
        yield  # type: ignore[misc]

    svc.subscribe_messages = _subscribe
    return svc


@pytest.fixture
def orchestrator_client(
    mock_orchestrator_svc: MagicMock,
) -> Generator[TestClient, None, None]:
    """TestClient for the orchestrator app with a mocked OrchestratorService."""

    @asynccontextmanager
    async def _lifespan(
        app: FastAPI,
    ) -> AsyncGenerator[dict[str, MagicMock], None]:
        yield {'service': mock_orchestrator_svc}

    test_app = FastAPI(lifespan=_lifespan)
    for route in _orch_app.routes:
        test_app.routes.append(route)

    with TestClient(test_app) as client:
        yield client
