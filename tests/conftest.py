import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from utils import make_persona

from services.agent.app import get_agent_info
from services.agent.config import AgentSettings
from services.agent.core.service import AgentService
from shared.models import AgentInfo, PersonaType


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
