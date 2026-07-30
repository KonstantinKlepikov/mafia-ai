from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from config import MafiaSettings
from core.game import Game, Shared
from data.database import Database
from schemas import AgentRole, AgentStateIn, AgentStatus, GamePhase


@pytest.fixture(scope='function')
def shared(game_id: int) -> MagicMock:
    s = MagicMock()
    s.agents = {}
    s.game_id = game_id
    return s


@pytest.fixture(scope='function')
def game_instance(
    db: Database,
    settings: MafiaSettings,
    shared: Shared,
) -> Game:
    llm = Mock()
    game = Game(
        settings=settings,
        llm=llm,
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
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(
            state=state,
            persona=persona,
            game_id=game_instance.shared.game_id,
        )

        assert agent.agent_id == 1, 'wrong agent id'
        stored_state = await db.get_agent_state(agent_id=agent.agent_id)
        assert stored_state.role == AgentRole.CITIZEN, 'wrong role persisted'
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
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(
            state=state,
            persona=persona,
            game_id=game_instance.shared.game_id,
        )
        game_instance.shared.agents[agent.agent_id] = agent

        await game_instance.eliminate_agent(agent_id=agent.agent_id)

        assert agent.agent_id not in game_instance.shared.agents, (
            'agent logic should be removed'
        )
        stored_state = await db.get_agent_state(agent_id=agent.agent_id)
        assert stored_state.status == AgentStatus.ELIMINATED, (
            'agent status should be updated in the database'
        )

    async def test_generate_message_delegates_to_agent_logic(
        self,
        db: Database,
        game_instance: Game,
    ) -> None:
        """Test generate_message forwards the call to the registered agent logic."""
        persona = await db.get_persona(1)
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(
            state=state,
            persona=persona,
            game_id=game_instance.shared.game_id,
        )
        expected_text = 'generated text'
        mock_logic = Mock()
        mock_logic.generate_message = AsyncMock(return_value=expected_text)
        game_instance.shared.agents[agent.agent_id] = mock_logic

        result = await game_instance.generate_message(
            agent_id=agent.agent_id,
            phase=GamePhase.DAY,
            game_round=2,
        )

        assert result == expected_text, 'wrong message text returned'
        mock_logic.generate_message.assert_awaited_once_with(
            phase=GamePhase.DAY,
            game_round=2,
        )

    async def test_generate_message_raises_for_unknown_agent(
        self,
        game_instance: Game,
    ) -> None:
        """Test generate_message raises KeyError when the agent is not registered."""
        with pytest.raises(KeyError):
            await game_instance.generate_message(
                agent_id=999,
                phase=GamePhase.NIGHT,
                game_round=1,
            )

    async def test_answer_question_delegates_to_agent_logic(
        self,
        db: Database,
        game_instance: Game,
    ) -> None:
        """Test answer_question forwards the call to the registered agent logic."""
        persona = await db.get_persona(1)
        state = AgentStateIn(
            role=AgentRole.CITIZEN,
            status=AgentStatus.ALIVE,
            persona_id=persona.persona_id,
        )

        agent = await game_instance.initialize_agent(
            state=state,
            persona=persona,
            game_id=game_instance.shared.game_id,
        )
        expected_answer = 'answer text'
        mock_logic = Mock()
        mock_logic.answer_question = AsyncMock(return_value=expected_answer)
        game_instance.shared.agents[agent.agent_id] = mock_logic

        result = await game_instance.answer_question(
            agent_id=agent.agent_id,
            question_text='Who is the mafia?',
        )

        assert result == expected_answer, 'wrong answer text returned'
        mock_logic.answer_question.assert_awaited_once_with('Who is the mafia?')
