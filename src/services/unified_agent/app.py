from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel

from shared.database import Database
from shared.models import AgentRole, AgentState

from .config import UnifiedAgentSettings
from .core.manager import AgentManager


class InitRequest(BaseModel):
    """Request to initialize a new agent.

    Attrs:
        role: Agent role (MAFIA or CITIZEN).
        persona_id: Persona ID from config/prompts.yaml.

    """

    role: AgentRole
    persona_id: str


class ActRequest(BaseModel):
    """Request to execute an agent action.

    Attrs:
        action: Action type ('generate_message', 'vote',
            'answer_question', 'add_message').
        params: Action-specific parameters.

    """

    action: str
    params: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown."""

    settings = UnifiedAgentSettings()

    db = Database()
    await db.connect()

    yaml_path = Path(settings.db_yaml_path)
    await db.init_from_yaml(yaml_path)

    manager = AgentManager(llm_url=settings.llm_url, db=db)

    logger.info(
        f'Unified Agent Service started (LLM: {settings.llm_url}, '
        f'YAML: {settings.db_yaml_path})'
    )

    try:
        yield {'manager': manager}
    finally:
        await manager.close()
        await db.close()

    logger.info('Unified Agent Service stopped')


app = FastAPI(title='Unified Agent Service', version='1.0.0', lifespan=lifespan)


@app.get('/health')
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status message.

    """
    return {'status': 'ok'}


@app.post('/agents/{agent_id}/init', status_code=status.HTTP_201_CREATED)
async def initialize_agent(
    agent_id: str,
    request: Request,
    init_request: InitRequest,
) -> dict[str, str]:
    """Initialize a new agent.

    Args:
        agent_id: Unique agent identifier.
        init_request: Initialization parameters.

    Returns:
        Status message.

    Raises:
        HTTPException: If manager not initialized or persona not found.

    """
    try:
        await request.state.manager.initialize_agent(
            agent_id,
            init_request.role,
            init_request.persona_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.__str__())

    return {'status': 'created', 'agent_id': agent_id}


@app.post('/agents/{agent_id}/act')
async def agent_act(
    agent_id: str, request: Request, act_request: ActRequest
) -> dict[str, Any]:
    """Execute an action for a specific agent.

    Args:
        agent_id: Agent to act.
        act_request: Action parameters.

    Returns:
        Action result.

    Raises:
        HTTPException: If agent not initialized or action fails.

    """
    try:
        result = await request.state.manager.act(
            agent_id,
            act_request.action,
            act_request.params,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.__str__(),
        )
    except Exception as exc:
        logger.error(f'Agent {agent_id} action {act_request.action} failed: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Action failed',
        )

    return result


@app.get('/agents/{agent_id}/state')
async def get_agent_state(agent_id: str, request: Request) -> AgentState:
    """Get current agent state.

    Args:
        agent_id: Agent to query.

    Returns:
        Agent state with role, persona, and message history.

    Raises:
        HTTPException: If agent not found.

    """
    try:
        state = await request.state.manager.get_state(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.__str__())

    return state


@app.delete('/agents/{agent_id}', status_code=status.HTTP_204_NO_CONTENT)
async def eliminate_agent(agent_id: str, request: Request) -> None:
    """Eliminate an agent (mark as eliminated and remove from manager).

    Args:
        agent_id: Agent to eliminate.

    Raises:
        HTTPException: If manager not initialized.

    """
    await request.state.manager.eliminate(agent_id)
