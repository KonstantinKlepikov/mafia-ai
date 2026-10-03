import pytest

from core import Database
from schemas import (
    AgentState,
    AgentStateInit,
    AgentStatus,
    AgentSummary,
    GamePhase,
    GameState,
    Message,
    Role,
    SummaryType,
    TargetAudience,
)
from schemas.constants import ALL


class TestDatabaseInit:
    """Test connections and init"""

    async def test_database_connect_and_close(self, db: Database) -> None:
        """Test database connection lifecycle."""
        assert db._conn is not None, 'connection must be established'
        await db.close()
        assert db._conn is None, 'connection must be closed'


class TestDatabaseGame:
    """Test game and game state methods"""

    async def test_update_game_and_game_state(self, db: Database, game) -> None:
        """Test storing and retrieving game state."""
        await db.update_game(round=3, phase=GamePhase.DAY_VOTE)
        game_state = await db.get_game_state()
        assert game_state is not None, 'game not finded'
        assert isinstance(game_state, GameState), 'wrong game state type'
        assert game_state.round == 3, 'wrong round'
        assert game_state.phase == GamePhase.DAY_VOTE, 'wrong phase'

    async def test_update_game_phase(self, db: Database, game) -> None:
        """Test updating only the game phase."""
        await db.update_game_phase(phase=GamePhase.DAY_VOTE)
        game_state = await db.get_game_state()
        assert isinstance(game_state, GameState), 'wrong game state type'
        assert game_state.phase == GamePhase.DAY_VOTE, 'wrong phase after update'

    async def test_update_game_round(self, db: Database, game) -> None:
        """Test updating only the game round."""
        await db.update_game_round(round=5)
        game_state = await db.get_game_state()
        assert isinstance(game_state, GameState), 'wrong game state type'
        assert game_state.round == 5, 'wrong round after update'

    async def test_get_game_state_defaults(self, db: Database, game) -> None:
        """Test new game should have round=1 and phase=NIGHT and empty agent lists."""
        gs = await db.get_game_state()
        assert isinstance(gs, GameState), 'wrong game state type'
        assert gs.round == 1, 'expected default round 1'
        assert gs.phase == GamePhase.NIGHT, 'expected default phase NIGHT'
        assert gs.alive == [], 'expected no alive agents'
        assert gs.eliminated == ALL, 'expected no eliminated agents'
        assert gs.mafia == [], 'expected empty mafia list'
        assert gs.citizen == [], 'expected empty citizen list'

    async def test_get_game_state_agents_aggregation(self, db: Database, game) -> None:
        """Test get_game_state should list alive and eliminated agent ids correctly."""
        a1 = await db.init_agent(
            state=AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        )
        a2 = await db.init_agent(
            state=AgentStateInit(id=2, role=Role.MAFIA, persona_id=2)
        )
        a3 = await db.init_agent(
            state=AgentStateInit(id=6, role=Role.CITIZEN, persona_id=3)
        )

        # eliminate agent 2
        await db.update_agent_status(agent_id=a2, status=AgentStatus.ELIMINATED)

        gs = await db.get_game_state()
        assert isinstance(gs, GameState), 'wrong game state type'
        assert gs.alive == [a1, a3], f'unexpected alive list: {gs.alive}'
        assert a2 in gs.eliminated, f'unexpected eliminated list {gs.eliminated}'
        assert gs.mafia == [], 'nonempty mafia list'
        assert gs.citizen == [a1, a3], 'empty citizen list'


class TestDatabaseAgent:
    """Test agent and agent state methods"""

    async def test_init_and_get_agent_state(self, db: Database, game) -> None:
        """Test inserting and retrieving agent state."""
        state = AgentStateInit(
            id=5,
            role=Role.CITIZEN,
            persona_id=2,
        )
        agent_id = await db.init_agent(state=state)
        assert agent_id == 5, 'wrong agent id'
        await db.insert_message(
            Message(
                agent_id=agent_id, content='this', phase=GamePhase.GAME_OVER, round=7
            )
        )
        retrieved = await db.get_agent_state(agent_id=agent_id)
        assert retrieved is not None, 'agent not finded'
        assert isinstance(retrieved, AgentState), 'wrong result type'
        assert retrieved.agent_id == agent_id, 'wrong agent id'
        assert retrieved.role == Role.CITIZEN, 'wronmg role'
        assert retrieved.status == AgentStatus.ALIVE, 'wronmg status'
        assert retrieved.persona_id == 2, 'wrong persona id'
        assert len(retrieved.message_history) == 1, 'wrong message hystory'

    async def test_update_agent_status_and_get_agent_state(
        self,
        db: Database,
        game,
    ) -> None:
        """Test updating agent status."""
        state = AgentStateInit(
            id=5,
            role=Role.CITIZEN,
            persona_id=5,
        )
        agent_id = await db.init_agent(state=state)
        assert agent_id == 5, 'wrong agent id'
        await db.insert_message(
            Message(
                agent_id=agent_id, content='this', phase=GamePhase.GAME_OVER, round=7
            )
        )
        await db.update_agent_status(agent_id=agent_id, status=AgentStatus.ELIMINATED)
        retrieved = await db.get_agent_state(agent_id=agent_id)
        assert isinstance(retrieved, AgentState), 'wrong result type'
        assert retrieved.status == AgentStatus.ELIMINATED, 'wronmg status'

    async def test_agents_summary_enforces_unique_agent_id(
        self,
        db: Database,
        game,
    ) -> None:
        """Test each agent_id has only one summary row (unique constraint)."""
        agent_id = await db.init_agent(
            state=AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        )

        with pytest.raises(Exception, match='UNIQUE constraint failed'):
            await db.conn.execute(
                """
                INSERT INTO agents_summary (agent_id, messages, questions, answers)
                VALUES (?, ?, ?, ?)
                """,
                (agent_id, 'msg2', 'q2', 'a2'),
            )
            await db.conn.commit()

    async def test_get_agent_summary_returns_empty_then_raises(
        self,
        db: Database,
        game,
    ) -> None:
        """Test get_agent_summary returns empty fields after init,
        then raises when missing."""
        agent_id = await db.init_agent(
            state=AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        )

        summary = await db.get_agent_summary(agent_id=agent_id)
        assert isinstance(summary, AgentSummary), f'wrong result type: {type(summary)}'
        assert summary.agent_id == agent_id, f'wrong agent_id: {summary.agent_id}'
        assert summary.messages == '', f'unexpected messages: {summary.messages}'
        assert summary.questions == '', f'unexpected questions: {summary.questions}'
        assert summary.answers == '', f'unexpected answers: {summary.answers}'

        await db.conn.execute(
            'DELETE FROM agents_summary WHERE agent_id = ?', (agent_id,)
        )
        await db.conn.commit()

        with pytest.raises(ValueError, match='Agent summary not found'):
            await db.get_agent_summary(agent_id=agent_id)

    async def test_agent_state_not_found(self, db: Database) -> None:
        """Test get_agent_state raises ValueError for unknown ID."""
        with pytest.raises(ValueError, match='Agent not found'):
            await db.get_agent_state(999)

    @pytest.mark.parametrize(
        'summary_type',
        [
            SummaryType.MESSAGES,
            SummaryType.QUESTIONS,
            SummaryType.ANSWERS,
        ],
    )
    async def test_update_agent_summary_parametrized(
        self,
        db: Database,
        summary_type: SummaryType,
        game,
    ) -> None:
        """Parametrized: update_agent_summary updates the correct column."""
        agent_id = await db.init_agent(
            state=AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        )

        value = f'updated-{summary_type.value}'
        await db.update_agent_summary(
            agent_id=agent_id,
            summary=value,
            summary_type=summary_type,
        )

        summary = await db.get_agent_summary(agent_id=agent_id)
        assert getattr(summary, summary_type.value) == value, (
            f'expected {summary_type.value} == {value}, '
            f'got: {getattr(summary, summary_type.value)}'
        )
        other_fields = {
            f for f in ('messages', 'questions', 'answers') if f != summary_type.value
        }
        for f in other_fields:
            assert getattr(summary, f) == '', f'expected other field {f} to be empty'


class TestDatabaseMessage:
    """Test message and message state methods"""

    async def test_insert_message_and_get_history(self, db: Database, game) -> None:
        """Test inserting a message and retrieving it from history."""
        state = AgentStateInit(
            id=5,
            role=Role.CITIZEN,
            persona_id=2,
        )
        msg = Message(
            agent_id=5,
            content='hello world',
            phase=GamePhase.NIGHT,
            round=1,
        )

        agent_id = await db.init_agent(state=state)
        assert agent_id == 5, 'wrong agent id'
        msg_id = await db.insert_message(msg)
        assert msg_id == 1, 'wrong message id'

        history = await db.get_message_hystory(agent_id=5)
        assert isinstance(history, list), 'wrong result type'
        assert len(history) == 1, 'wrong history length'
        retrieved = history[0]
        assert retrieved.agent_id == 5, 'wrong sender id'
        assert retrieved.content == 'hello world', 'wrong content'
        assert retrieved.phase == GamePhase.NIGHT, 'wrong phase'
        assert retrieved.round == 1, 'wrong round'
        assert retrieved.target == TargetAudience.ALL, 'wrong target'

    async def test_get_agents_state_aggregates_messages(
        self,
        db: Database,
        game,
    ) -> None:
        """
        Test get_agents_state returns agents with aggregated message histories.
        """
        state1 = AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        state2 = AgentStateInit(id=2, role=Role.MAFIA, persona_id=2)
        agent1 = await db.init_agent(state=state1)
        agent2 = await db.init_agent(state=state2)
        await db.insert_message(
            Message(agent_id=agent1, content='a1-m1', phase=GamePhase.NIGHT, round=1),
        )
        await db.insert_message(
            Message(agent_id=agent1, content='a1-m2', phase=GamePhase.DAY, round=2),
        )
        await db.insert_message(
            Message(agent_id=agent2, content='a2-m1', phase=GamePhase.DAY, round=2),
        )

        agents = await db.get_agents_state(status=AgentStatus.ALIVE)

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

    async def test_get_agents_state_no_messages(self, db: Database, game) -> None:
        """
        Test get_agents_state with no messages.
        """
        state1 = AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        state2 = AgentStateInit(id=2, role=Role.MAFIA, persona_id=2)
        agent1 = await db.init_agent(state=state1)
        agent2 = await db.init_agent(state=state2)
        await db.insert_message(
            Message(agent_id=agent1, content='a1-m2', phase=GamePhase.DAY, round=1)
        )

        agents = await db.get_agents_state(status=AgentStatus.ALIVE)

        # find agent entries and validate message counts and contents
        a1 = next(a for a in agents if a.agent_id == agent1)
        a2 = next(a for a in agents if a.agent_id == agent2)

        assert len(a1.message_history) == 1, 'agent1 should have 1 message'
        assert len(a2.message_history) == 0, 'agent2 should have 0 messages'


class TestDatabaseClear:
    """Test Database.clear method"""

    async def test_clear_removes_rows_and_resets_sequence(
        self,
        db: Database,
        game,
    ) -> None:
        """Test clear() deletes temporal data and resets AUTOINCREMENT."""
        await db.update_game_round(round=3)
        state = AgentStateInit(id=5, role=Role.CITIZEN, persona_id=2)
        agent_id = await db.init_agent(state=state)

        # ensure data exists
        game_state = await db.get_game_state()
        assert agent_id in game_state.alive, 'expected alive'
        assert game_state.round == 3, 'wrong game round'

        # clear DB
        await db.clear()

        # no agents after clear
        await db.init_game()
        game_state = await db.get_game_state()
        assert agent_id not in game_state.alive, 'unexpected alive'
        assert game_state.round == 1, 'wrong game round'
