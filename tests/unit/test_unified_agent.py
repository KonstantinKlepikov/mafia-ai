"""Unit tests for Unified Agent Service."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from shared.database import Database
from shared.models import AgentRole, AgentState, GamePhase
from services.unified_agent.core.agent_logic import AgentLogic
from services.unified_agent.core.manager import AgentManager


@pytest.fixture
async def db() -> Database:
    """Create in-memory database with test personas.

    Yields:
        Initialized database instance.

    """
    database = Database()
    await database.connect()

    # Insert test persona manually
    cursor = await database._conn.execute(
        'INSERT INTO personas (id, name, type, prompt) VALUES (?, ?, ?, ?)',
        ('test-persona', 'test_persona', 'test_type', 'You are a test character.'),
    )
    await database._conn.commit()

    yield database

    await database.close()


@pytest.fixture
def mock_llm_client() -> httpx.AsyncClient:
    """Create mock LLM HTTP client.

    Returns:
        Mock async HTTP client.

    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = Mock()
    mock_response.json.return_value = {'text': 'Hello, I am a test agent!'}
    mock_response.raise_for_status = Mock()
    mock_client.post.return_value = mock_response
    return mock_client


@pytest.mark.asyncio
async def test_agent_manager_initialize_agent(db: Database) -> None:
    """Test agent initialization in manager."""
    manager = AgentManager(llm_url='http://llm:8003', db=db)

    await manager.initialize_agent(
        agent_id='agent-1', role=AgentRole.CITIZEN, persona_id='test-persona'
    )

    state = await manager.get_state('agent-1')
    assert state.agent_id == 'agent-1'
    assert state.role == AgentRole.CITIZEN
    assert state.persona_id == 'test-persona'

    await manager.close()


@pytest.mark.asyncio
async def test_agent_logic_generate_message(
    db: Database, mock_llm_client: httpx.AsyncClient
) -> None:
    """Test message generation in agent logic."""
    persona = await db.get_persona('test-persona')
    agent = AgentLogic(
        agent_id='agent-1',
        persona=persona,
        llm_client=mock_llm_client,
        db=db,
    )

    # Initialize agent state
    state = AgentState(
        agent_id='agent-1',
        role=AgentRole.CITIZEN,
        persona_id='test-persona',
        message_history=[],
    )
    await db.upsert_agent_state('agent-1', state)

    message = await agent.generate_message(phase=GamePhase.DAY, game_round=1)

    assert message == 'Hello, I am a test agent!'
    mock_llm_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_agent_manager_act_generate_message(db: Database) -> None:
    """Test manager act method with generate_message action."""
    manager = AgentManager(llm_url='http://llm:8003', db=db)

    await manager.initialize_agent(
        agent_id='agent-1', role=AgentRole.CITIZEN, persona_id='test-persona'
    )

    # Mock LLM client response
    mock_response = Mock()
    mock_response.json.return_value = {'text': 'Test message'}
    mock_response.raise_for_status = Mock()
    manager._llm_client.post = AsyncMock(return_value=mock_response)

    result = await manager.act(
        agent_id='agent-1',
        action='generate_message',
        params={'phase': GamePhase.DAY, 'round': 1},
    )

    assert result['message'] == 'Test message'

    await manager.close()


@pytest.mark.asyncio
async def test_agent_manager_eliminate(db: Database) -> None:
    """Test agent elimination."""
    manager = AgentManager(llm_url='http://llm:8003', db=db)

    await manager.initialize_agent(
        agent_id='agent-1', role=AgentRole.CITIZEN, persona_id='test-persona'
    )

    await manager.eliminate('agent-1')

    with pytest.raises(ValueError, match='Agent agent-1 not initialized'):
        await manager.get_state('agent-1')

    await manager.close()


@pytest.mark.asyncio
async def test_agent_manager_act_unknown_action(db: Database) -> None:
    """Test manager act method with unknown action."""
    manager = AgentManager(llm_url='http://llm:8003', db=db)

    await manager.initialize_agent(
        agent_id='agent-1', role=AgentRole.CITIZEN, persona_id='test-persona'
    )

    with pytest.raises(ValueError, match='Unknown action'):
        await manager.act(agent_id='agent-1', action='unknown_action', params={})

    await manager.close()
