import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from shared.models import AgentInfo, GameState, HostDecision
from shared.telemetry import configure_loguru, instrument_app, setup_tracing

from .config import OrchestratorSettings
from .core.service import OrchestratorService

_SERVICE_NAME = 'orchestrator'
setup_tracing(_SERVICE_NAME)
configure_loguru(_SERVICE_NAME)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[dict[str, OrchestratorService]]:
    settings = OrchestratorSettings()
    service = OrchestratorService(settings)
    try:
        await service.start()
    except Exception as exc:
        logger.error(f'OrchestratorService failed to start: {exc}')
    logger.info('Orchestrator HTTP server ready')
    try:
        yield {'service': service}
    finally:
        await service.stop()


app = FastAPI(
    title='Orchestrator Service',
    description='Mafia-AI game orchestrator — manages game cycle and agents.',
    version='0.1.0',
    lifespan=_lifespan,
)
instrument_app(app, _SERVICE_NAME)


def _svc(request: Request) -> OrchestratorService:
    return request.state.service


# ------------------------------------------------------------------
# Game endpoints
# ------------------------------------------------------------------


@app.post('/game/start', status_code=200)
async def start_game(request: Request) -> dict[str, str]:
    """Start a new game.

    Assigns roles, sends init messages to agents and launches the game loop.
    Returns 409 if a game is already in progress.
    """
    try:
        await _svc(request).begin_game()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'status': 'started'}


@app.get('/game/state', response_model=GameState)
async def get_game_state(request: Request) -> GameState:
    """Return the current game state (phase, round, alive/eliminated agents)."""
    return _svc(request).get_game_state()


@app.post('/game/host/decision', status_code=200)
async def host_decision(request: Request, decision: HostDecision) -> dict[str, str]:
    """Submit a host decision for the current HOST_DECISION phase.

    Actions:
    - ``APPROVE``: eliminate the majority-voted agent.
    - ``REJECT``: no elimination this round.
    - ``OVERRIDE``: eliminate a specific agent (``target_id`` required).
    """
    _svc(request).submit_host_decision(decision)
    return {'status': 'accepted'}


@app.get('/game/messages')
async def stream_messages(request: Request) -> StreamingResponse:
    """Stream all game messages as Server-Sent Events.

    Replays the full message history first, then streams new messages in
    real time. Each event is a JSON-encoded ``Message`` object.
    """
    service = _svc(request)

    async def _event_generator() -> AsyncGenerator[str, None]:
        async for msg in service.subscribe_messages():
            yield f'data: {msg.model_dump_json()}\n\n'

    return StreamingResponse(_event_generator(), media_type='text/event-stream')


# ------------------------------------------------------------------
# Agent endpoints
# ------------------------------------------------------------------


@app.get('/game/agents', response_model=dict[str, AgentInfo])
async def get_agents(request: Request) -> dict[str, AgentInfo]:
    """Poll all alive agents and return their current info."""
    return await _svc(request).get_agents_info()


@app.get('/game/agents/{agent_id}', response_model=AgentInfo)
async def get_agent(request: Request, agent_id: str) -> AgentInfo:
    """Return the current info for a specific agent.

    Returns 404 if the agent is unknown or its container is unreachable.
    """
    info = await _svc(request).get_agent_info(agent_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f'Agent {agent_id!r} not found or unreachable',
        )
    return info


class _QuestionRequest(BaseModel):
    question_text: str


@app.post('/game/agents/{agent_id}/question', status_code=202)
async def ask_agent_question(
    request: Request,
    agent_id: str,
    body: _QuestionRequest,
) -> dict[str, str]:
    """Ask an agent a question on behalf of the host.

    Publishes a ``HostQuestion`` message to the agent via RabbitMQ and
    returns a ``question_id`` that can be used to retrieve the answer.
    """
    question_id = str(uuid.uuid4())
    await _svc(request).ask_agent(agent_id, question_id, body.question_text)
    return {'question_id': question_id}


@app.get('/game/agents/{agent_id}/question/{question_id}')
async def get_agent_answer(
    request: Request,
    agent_id: str,
    question_id: str,
) -> dict[str, str]:
    """Poll for an agent's answer to a previously submitted question.

    Waits up to 60 seconds. Returns 408 if no answer arrives in time.
    """
    answer = await _svc(request).get_agent_answer(question_id, timeout=60.0)
    if answer is None:
        raise HTTPException(
            status_code=408,
            detail=f'Answer for question {question_id!r} not received within timeout',
        )
    return {'answer': answer}


@app.delete('/game/agents/{agent_id}', status_code=200)
async def force_stop_agent(request: Request, agent_id: str) -> dict[str, str]:
    """Force-eliminate an agent and stop its Docker container.

    Use for emergency removal outside the normal game flow.
    """
    await _svc(request).force_stop_agent(agent_id)
    return {'status': 'stopped', 'agent_id': agent_id}
