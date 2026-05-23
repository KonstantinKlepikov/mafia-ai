from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from loguru import logger

from shared.models import AgentInfo

from .config import AgentSettings
from .core.service import AgentService


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[dict[str, AgentService], None]:
    settings = AgentSettings()
    service = AgentService(settings)
    try:
        await service.start()
    except Exception as exc:
        # Log the error but still yield so the HTTP server stays up;
        # GET /agent/info will return default state.
        logger.error(f'AgentService failed to start: {exc}')
    logger.info(f'Agent {settings.agent_id} HTTP server ready')
    try:
        yield {'service': service}
    finally:
        await service.stop()


app = FastAPI(
    title='Agent Service',
    description='Single Mafia-AI agent exposing its current state.',
    version='0.1.0',
    lifespan=_lifespan,
)


@app.get('/agent/info', response_model=AgentInfo)
async def get_agent_info(request: Request) -> AgentInfo:
    """Return current agent metadata.

    Used by the orchestrator to poll living agents' state.
    """
    service: AgentService = request.state.service
    return service.get_info()
