import pytest

from shared.database import Database
from shared.models import (
    AgentRole,
    AgentStateIn,
    AgentStateOut,
    AgentStatus,
    GamePhase,
    GameState,
    Message,
    SystemPrompt,
    TargetAudience,
)


class TestDatabase:
    """Test connections and crud"""

    async def test_database_connect_and_close(self, db: Database) -> None:
        """Test database connection lifecycle."""
        assert db._conn is not None, 'connection must be established'
        await db.close()
        assert db._conn is None, 'connection must be closed'

    async def test_init_from_yaml(self, db: Database) -> None:
        """Test loading personas from YAML config."""
        personas = await db.get_personas()
        assert len(personas) == 11, 'expected 11 personas from config'
        assert personas[0].persona_id == 1, 'wrong persona_id'
        assert personas[0].name == 'system', 'wrong system persona name'
        assert personas[1].name == 'persona_1_good_natured', 'wrong persona name'

    async def test_get_persona(self, db: Database) -> None:
        """Test retrieving a single persona by ID."""
        persona = await db.get_persona(3)
        assert isinstance(persona, SystemPrompt), ' wrong result type'
        assert persona.persona_id == 3, 'wrong persona id'
        assert persona.name == 'persona_2_hysteric', 'wrong persona name'
        assert persona.persona_type == 'hysteric', 'wrong persona type'
        assert len(persona.prompt) > 0, 'wrong prompt'

    async def test_get_personas(self, db: Database) -> None:
        """Test retrieving a single persona by ID."""
        personas = await db.get_personas()
        assert isinstance(personas, list), ' wrong result type'
        assert isinstance(personas[0], SystemPrompt), ' wrong subtype'
        assert len(personas) == 11, 'wrong personas len'

    async def test_get_persona_not_found(self, db: Database) -> None:
        """Test get_persona raises ValueError for unknown ID."""
        with pytest.raises(ValueError, match='Persona not found'):
            await db.get_persona(999)

    async def test_init_new_game(self, db: Database) -> None:
        """Test init game"""
        game_id = await db.init_game()
        assert game_id == 1, 'wrong game id'

    async def test_update_game_and_game_state(self, db: Database) -> None:
        """Test storing and retrieving game state."""
        game_id = await db.init_game()
        assert game_id == 1, 'wrong game id'
        await db.update_game(
            game_id=game_id,
            round=3,
            phase=GamePhase.DAY_VOTE,
        )
        game_state = await db.get_game_state(game_id=game_id)
        assert game_state is not None, 'game not finded'
        assert isinstance(game_state, GameState), 'wrong game state type'
        assert game_state.game_id == game_id, 'wrong game id'
        assert game_state.round == 3, 'wrong round'
        assert game_state.phase == GamePhase.DAY_VOTE, 'wrong phase'

    async def test_game_state_not_found(self, db: Database) -> None:
        """Test get_game_state raises ValueError for unknown ID."""
        with pytest.raises(ValueError, match='Game not found'):
            await db.get_game_state(999)

    async def test_init_and_get_agent_state(self, db: Database) -> None:
        """Test inserting and retrieving agent state."""
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            persona_id=1,
        )

        game_id = await db.init_game()
        assert game_id == 1, 'wrong game id'
        agent_id = await db.init_agent(state=state, game_id=game_id)
        assert agent_id == 1, 'wrong agent id'
        assert agent_id == 1, 'wrong agent id'
        await db.insert_message(
            Message(
                sender_id=agent_id, content='this', phase=GamePhase.GAME_OVER, round=7
            )
        )
        retrieved = await db.get_agent_state(agent_id=agent_id)
        assert retrieved is not None, 'agent not finded'
        assert isinstance(retrieved, AgentStateOut), 'wrong result type'
        assert retrieved.agent_id == agent_id, 'wrong agent id'
        assert retrieved.role == AgentRole.CITIZEN, 'wronmg role'
        assert retrieved.status == AgentStatus.ALIVE, 'wronmg status'
        assert retrieved.persona_id == 1, 'wrong persona id'
        assert len(retrieved.message_history) == 1, 'wrong message hystory'

    async def test_update_agent_status_and_get_agent_state(self, db: Database) -> None:
        """Test updating agent status."""
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            persona_id=4,
        )

        game_id = await db.init_game()
        assert game_id == 1, 'wrong game id'
        agent_id = await db.init_agent(state=state, game_id=game_id)
        assert agent_id == 1, 'wrong agent id'
        await db.insert_message(
            Message(
                sender_id=agent_id, content='this', phase=GamePhase.GAME_OVER, round=7
            )
        )
        await db.update_agent_status(agent_id=agent_id, status=AgentStatus.ELIMINATED)
        retrieved = await db.get_agent_state(agent_id=agent_id)
        assert isinstance(retrieved, AgentStateOut), 'wrong result type'
        assert retrieved.status == AgentStatus.ELIMINATED, 'wronmg status'

    async def test_agent_state_not_found(self, db: Database) -> None:
        """Test get_agent_state raises ValueError for unknown ID."""
        with pytest.raises(ValueError, match='Agent not found'):
            await db.get_agent_state(999)

    async def test_insert_message_and_get_history(self, db: Database) -> None:
        """Test inserting a message and retrieving it from history."""
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            persona_id=1,
        )
        msg = Message(
            sender_id=1,
            content='hello world',
            phase=GamePhase.NIGHT,
            round=1,
        )

        game_id = await db.init_game()
        assert game_id == 1, 'wrong game id'
        agent_id = await db.init_agent(state=state, game_id=game_id)
        assert agent_id == 1, 'wrong agent id'
        msg_id = await db.insert_message(msg)
        assert msg_id == 1, 'wrong message id'

        history = await db.get_message_hystory(agent_id=1)
        assert isinstance(history, list), 'wrong result type'
        assert len(history) == 1, 'wrong history length'
        retrieved = history[0]
        assert retrieved.sender_id == 1, 'wrong sender id'
        assert retrieved.content == 'hello world', 'wrong content'
        assert retrieved.phase == GamePhase.NIGHT, 'wrong phase'
        assert retrieved.round == 1, 'wrong round'
        assert retrieved.target_audience == TargetAudience.ALL, 'wrong target'

    async def test_get_agents_state_aggregates_messages(self, db: Database) -> None:
        """
        Test that get_agents_state returns agents with aggregated message histories.
        """
        game_id = await db.init_game()
        assert game_id == 1
        state1 = AgentStateIn(role=AgentRole.CITIZEN, persona_id=1)
        state2 = AgentStateIn(role=AgentRole.MAFIA, persona_id=2)
        agent1 = await db.init_agent(state=state1, game_id=game_id)
        agent2 = await db.init_agent(state=state2, game_id=game_id)
        await db.insert_message(
            Message(sender_id=agent1, content='a1-m1', phase=GamePhase.NIGHT, round=1)
        )
        await db.insert_message(
            Message(sender_id=agent1, content='a1-m2', phase=GamePhase.DAY, round=2)
        )
        await db.insert_message(
            Message(sender_id=agent2, content='a2-m1', phase=GamePhase.DAY, round=2)
        )

        agents = await db.get_agents_state(game_id=game_id, status=AgentStatus.ALIVE)

        assert isinstance(agents, list), 'expected list result'
        ids = {a.agent_id for a in agents}
        assert agent1 in ids and agent2 in ids, 'agents not in alive'

        # find agent entries and validate message counts and contents
        a1 = next(a for a in agents if a.agent_id == agent1)
        a2 = next(a for a in agents if a.agent_id == agent2)

        assert len(a1.message_history) == 2, 'agent1 should have 2 messages'
        assert len(a2.message_history) == 1, 'agent2 should have 1 message'

        assert a1.message_history[0].content == 'a1-m1'
        assert a1.message_history[1].content == 'a1-m2'
        assert a2.message_history[0].content == 'a2-m1'
