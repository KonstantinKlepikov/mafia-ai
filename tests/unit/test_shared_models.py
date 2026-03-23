from shared.models import (
    AgentRole,
    AgentState,
    GamePhase,
    GameState,
    Message,
    TargetAudience,
    VoteEvent,
)


class TestSharedModels:
    """Tests for shared Pydantic models and enums."""

    def test_enums_values(self) -> None:
        """Test: enum values are stable and match expected strings"""
        assert AgentRole.CITIZEN.value == 'CITIZEN', (
            "AgentRole.CITIZEN value must be 'CITIZEN'"
        )
        assert AgentRole.MAFIA.value == 'MAFIA', "AgentRole.MAFIA value must be 'MAFIA'"
        assert GamePhase.NIGHT.value == 'NIGHT', "GamePhase.NIGHT value must be 'NIGHT'"

    def test_message_vote_and_agent_state(self) -> None:
        pass

    def test_message_construction(self) -> None:
        """Test: Message basic construction"""
        msg = Message(
            sender_id='agent-1',
            content='Hello world',
            phase=GamePhase.DAY,
            round=1,
            target_audience=TargetAudience.ALL,
        )
        assert msg.sender_id == 'agent-1', (
            'Message.sender_id should match the provided sender'
        )
        assert msg.content == 'Hello world', (
            'Message.content should match the provided text'
        )

    def test_vote_event_construction(self) -> None:
        """Test: VoteEvent basic construction"""
        vote = VoteEvent(
            voter_id='agent-1', target_id='agent-2', phase=GamePhase.DAY_VOTE, round=1
        )
        assert vote.target_id == 'agent-2', (
            'VoteEvent.target_id should match the provided target'
        )

    def test_game_state_basic(self) -> None:
        """Test: GameState contains listed alive agents"""
        gs = GameState(
            round=0,
            phase=GamePhase.NIGHT,
            alive_agents=['agent-1', 'agent-2'],
            eliminated=[],
        )
        assert 'agent-2' in gs.alive_agents, (
            'GameState.alive_agents must include provided agents'
        )

    def test_agent_state_message_history(self) -> None:
        """Test: AgentState retains message history"""
        msg = Message(
            sender_id='agent-1',
            content='Hello world',
            phase=GamePhase.DAY,
            round=1,
            target_audience=TargetAudience.ALL,
        )
        agent_state = AgentState(
            agent_id='agent-1',
            role=AgentRole.CITIZEN,
            persona_id='p1',
            message_history=[msg],
        )
        assert agent_state.message_history[0].content == 'Hello world', (
            'AgentState.message_history should preserve message content'
        )
