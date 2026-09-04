from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from ollama import AsyncClient

from config import MafiaSettings
from core import Database, Game, Shared
from schemas import AgentStateInit, AgentStatus, GamePhase, Role


@pytest.fixture(scope='function')
def shared(game) -> MagicMock:
    s = MagicMock()
    s.agents = {}
    return s


@pytest.fixture(scope='function')
def game_instance(
    db: Database,
    ollama_cl: AsyncClient,
    settings: MafiaSettings,
    shared: Shared,
) -> Game:
    game = Game(
        settings=settings,
        ollama=ollama_cl,
        event_bus=Mock(),
        db=db,
    )
    game.shared = shared
    return game


class TestGameAgentLifecycle:
    """Test game agent lifecycle methods."""

    async def test_initialize_agent_persists_state_and_registers_logic(
        self,
        db: Database,
        game_instance: Game,
    ) -> None:
        """Test initialize_agent stores state and creates an AgentLogic instance."""
        persona = await db.get_persona(1)
        state = AgentStateInit(
            role=Role.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(state=state, persona=persona)

        assert agent.agent_id == 1, 'wrong agent id'
        stored_state = await db.get_agent_state(agent_id=agent.agent_id)
        assert stored_state.role == Role.CITIZEN, 'wrong role persisted'
        assert stored_state.status == AgentStatus.ALIVE, 'wrong status persisted'
        assert stored_state.persona_id == persona.persona_id, (
            'wrong persona id persisted'
        )

    async def test_eliminate_agent_removes_logic_and_updates_status(
        self,
        db: Database,
        game_instance: Game,
    ) -> None:
        """Test eliminate_agent unregisters the agent and updates its state."""
        persona = await db.get_persona(1)
        state = AgentStateInit(
            role=Role.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(state=state, persona=persona)
        game_instance.shared.agents[agent.agent_id] = agent

        await game_instance.eliminate_agent(agent_id=agent.agent_id)

        assert agent.agent_id not in game_instance.shared.agents, (
            'agent logic should be removed'
        )
        stored_state = await db.get_agent_state(agent_id=agent.agent_id)
        assert stored_state.status == AgentStatus.ELIMINATED, (
            'agent status should be updated in the database'
        )

    async def test_transition_phase_updates_db_and_returns_state(
        self,
        game_instance: Game,
    ) -> None:
        """Test _transition_phase persists the new phase and returns the state."""
        expected_state = MagicMock()
        game_instance.db.update_game_phase = AsyncMock()  # type: ignore
        game_instance.db.get_game_state = AsyncMock(  # type: ignore
            return_value=expected_state
        )

        result = await game_instance._transition_phase(phase=GamePhase.DAY)

        game_instance.db.update_game_phase.assert_awaited_once_with(
            phase=GamePhase.DAY,
        )
        game_instance.db.get_game_state.assert_awaited_once_with()
        assert result is expected_state, 'not expected game state'
