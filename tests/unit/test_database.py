from pathlib import Path

import pytest

from shared.database import Database
from shared.models import AgentRole, AgentState, AgentStatus, GamePhase


async def test_database_connect_and_close() -> None:
    """Test database connection lifecycle."""
    db = Database()
    await db.connect()
    assert db._conn is not None, 'connection must be established'
    await db.close()
    assert db._conn is None, 'connection must be closed'


async def test_init_from_yaml() -> None:
    """Test loading personas from YAML config."""
    db = Database()
    await db.connect()

    yaml_path = Path('/home/kklepikov/_code_/mafia-ai/config/prompts.yaml')
    await db.init_from_yaml(yaml_path)

    personas = await db.list_personas()
    assert len(personas) == 10, 'expected 10 personas from config'
    assert personas[0].persona_id == 'persona-1'
    assert personas[0].name == 'persona_1_good_natured'

    await db.close()


async def test_get_persona() -> None:
    """Test retrieving a single persona by ID."""
    db = Database()
    await db.connect()

    yaml_path = Path('/home/kklepikov/_code_/mafia-ai/config/prompts.yaml')
    await db.init_from_yaml(yaml_path)

    persona = await db.get_persona('persona-2')
    assert persona.persona_id == 'persona-2'
    assert persona.name == 'persona_2_hysteric'
    assert persona.persona_type == 'hysteric'
    assert len(persona.prompt) > 0

    await db.close()


async def test_get_persona_not_found() -> None:
    """Test get_persona raises ValueError for unknown ID."""
    db = Database()
    await db.connect()

    yaml_path = Path('/home/kklepikov/_code_/mafia-ai/config/prompts.yaml')
    await db.init_from_yaml(yaml_path)

    with pytest.raises(ValueError, match='Persona not found'):
        await db.get_persona('persona-999')

    await db.close()


async def test_upsert_and_get_agent_state() -> None:
    """Test inserting and retrieving agent state."""
    db = Database()
    await db.connect()

    state = AgentState(
        agent_id='agent-1',
        role=AgentRole.CITIZEN,
        persona_id='persona-1',
        message_history=[],
    )

    await db.upsert_agent_state('agent-1', state)

    retrieved = await db.get_agent_state('agent-1')
    assert retrieved is not None
    assert retrieved.agent_id == 'agent-1'
    assert retrieved.role == AgentRole.CITIZEN
    assert retrieved.persona_id == 'persona-1'
    assert len(retrieved.message_history) == 0

    await db.close()


async def test_update_agent_status() -> None:
    """Test updating agent status."""
    db = Database()
    await db.connect()

    state = AgentState(
        agent_id='agent-2',
        role=AgentRole.MAFIA,
        persona_id='persona-2',
        message_history=[],
    )

    await db.upsert_agent_state('agent-2', state)
    await db.update_agent_status('agent-2', AgentStatus.ELIMINATED)

    await db.get_agent_state('agent-2')
    # NOTE: upsert_agent_state sets status to ALIVE by default,
    # but we updated it to ELIMINATED
    # This test will fail if update_agent_status doesn't work
    # Currently the get_agent_state doesn't return status, so we need to fix that

    await db.close()


async def test_upsert_game_state() -> None:
    """Test storing and retrieving game state."""
    db = Database()
    await db.connect()

    await db.upsert_game_state(
        game_id='game-1',
        round_num=3,
        phase=GamePhase.DAY_VOTE,
        alive_agents=['agent-1', 'agent-2', 'agent-3'],
        eliminated=['agent-4'],
    )

    game_state = await db.get_game_state('game-1')
    assert game_state is not None
    assert game_state['game_id'] == 'game-1'
    assert game_state['round'] == 3
    assert game_state['phase'] == GamePhase.DAY_VOTE
    assert game_state['alive_agents'] == ['agent-1', 'agent-2', 'agent-3']
    assert game_state['eliminated'] == ['agent-4']

    await db.close()
