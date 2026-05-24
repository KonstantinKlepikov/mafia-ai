from unittest.mock import AsyncMock, MagicMock

import pytest
from utils import game_state, make_persona

from services.agent.config import AgentSettings
from services.agent.core.service import AgentService
from shared.models import (
    AgentInit,
    AgentRole,
    AgentStatus,
    GamePhase,
    HostQuestion,
    Message,
    PersonaType,
    TargetAudience,
)


class TestAgentServiceInit:
    """Test AgentService init"""

    def test_initial_status_is_alive(self, service_with_persona: AgentService) -> None:
        """Test agent starts with ALIVE status before any game event."""
        assert service_with_persona._status == AgentStatus.ALIVE, (
            'initial status must be ALIVE'
        )

    def test_state_is_none_before_role_assignment(
        self, service_with_persona: AgentService
    ) -> None:
        """Test _state is None until game.init is received."""
        assert service_with_persona._state is None, (
            '_state must be None before role assignment'
        )

    def test_get_info_returns_citizen_role_by_default(
        self, service_with_persona: AgentService
    ) -> None:
        """Test get_info defaults to CITIZEN role when role not yet assigned."""
        info = service_with_persona.get_info()
        assert info.role == AgentRole.CITIZEN, (
            'default role must be CITIZEN before game.init is received'
        )

    def test_get_info_returns_agent_id(self, settings: AgentSettings) -> None:
        """Test get_info always returns the configured agent_id."""
        custom = AgentSettings(
            agent_id='agent-7',
            persona_id=settings.persona_id,
            amqp_url=settings.amqp_url,
            llm_url=settings.llm_url,
            vectordb_host=settings.vectordb_host,
            vectordb_port=settings.vectordb_port,
        )
        service = AgentService(settings=custom)
        service._AgentService__persona = make_persona(  # type: ignore[attr-defined]
            name='persona_1_good_natured',
            _id='uuid-test',
            _type=PersonaType.GOOD_NATURED,
            prompt='You are a kind-hearted villager.',
        )
        info = service.get_info()
        assert info.agent_id == 'agent-7', 'agent_id in info must match settings'

    def test_get_info_returns_persona_name(
        self, service_with_persona: AgentService
    ) -> None:
        """Test get_info returns the persona name loaded from VectorDB."""
        info = service_with_persona.get_info()
        assert info.persona_name == 'persona_1_good_natured', (
            'persona_name must match loaded persona'
        )

    def test_get_info_returns_alive_status_initially(
        self, service_with_persona: AgentService
    ) -> None:
        """Test get_info returns ALIVE status before any elimination event."""
        info = service_with_persona.get_info()
        assert info.status == AgentStatus.ALIVE, 'initial status in info must be ALIVE'


class TestOnGameInit:
    """Test AgentService._on_game_init"""

    @pytest.mark.asyncio
    async def test_citizen_role_assignment(
        self, service_with_persona: AgentService
    ) -> None:
        """Test _on_game_init sets CITIZEN role correctly."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        assert service_with_persona._state is not None, (
            'state must be set after game.init'
        )
        assert service_with_persona._state.role == AgentRole.CITIZEN, (
            'role must be CITIZEN'
        )

    @pytest.mark.asyncio
    async def test_mafia_role_assignment(
        self, service_with_persona: AgentService
    ) -> None:
        """Test _on_game_init sets MAFIA role correctly."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.MAFIA)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        assert service_with_persona._state is not None, (
            'state must be set after game.init'
        )
        assert service_with_persona._state.role == AgentRole.MAFIA, 'role must be MAFIA'

    @pytest.mark.asyncio
    async def test_mafia_subscribes_to_mafia_channel(
        self, service_with_persona: AgentService
    ) -> None:
        """Test MAFIA agent subscribes to message.mafia after role assignment."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.MAFIA)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        service_with_persona._messaging.subscribe.assert_awaited_once_with(
            'message.mafia', service_with_persona._on_message
        )

    @pytest.mark.asyncio
    async def test_citizen_does_not_subscribe_to_mafia_channel(
        self, service_with_persona: AgentService
    ) -> None:
        """Test CITIZEN agent does not subscribe to message.mafia."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        service_with_persona._messaging.subscribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_body_does_not_raise(
        self, service_with_persona: AgentService
    ) -> None:
        """Test malformed game.init body is handled gracefully without exception."""
        service_with_persona._messaging = MagicMock()
        await service_with_persona._on_game_init('game.init.agent-1', b'not-json')
        # No exception → test passes

    @pytest.mark.asyncio
    async def test_status_reset_to_alive_on_game_init(
        self, service_with_persona: AgentService
    ) -> None:
        """Test status is reset to ALIVE when a new game.init is received."""
        service_with_persona._status = AgentStatus.ELIMINATED
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        assert service_with_persona._status == AgentStatus.ALIVE, (
            'status must be reset to ALIVE on new game init'
        )


class TestOnMessage:
    """Test AgentService._on_message"""

    def _make_message(self, sender: str = 'agent-2', content: str = 'Hello') -> Message:
        return Message(
            sender_id=sender,
            content=content,
            phase=GamePhase.DAY,
            round=1,
            target_audience=TargetAudience.ALL,
        )

    @pytest.mark.asyncio
    async def test_message_from_other_agent_added_to_history(
        self, service_with_persona: AgentService
    ) -> None:
        """Test message from another agent is appended to message_history."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        msg = self._make_message(sender='agent-2')
        await service_with_persona._on_message(
            'message.all', msg.model_dump_json().encode()
        )

        assert service_with_persona._state is not None
        assert len(service_with_persona._state.message_history) == 1, (
            'one message must be in history after receiving one message'
        )

    @pytest.mark.asyncio
    async def test_own_message_not_added_to_history(
        self, service_with_persona: AgentService
    ) -> None:
        """Test message sent by this agent itself is not duplicated in history."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        msg = self._make_message(sender='agent-1')
        await service_with_persona._on_message(
            'message.all', msg.model_dump_json().encode()
        )

        assert service_with_persona._state is not None
        assert len(service_with_persona._state.message_history) == 0, (
            'own message must not be stored in history via _on_message'
        )

    @pytest.mark.asyncio
    async def test_message_ignored_when_state_is_none(
        self, service_with_persona: AgentService
    ) -> None:
        """Test messages received before game.init are silently dropped."""
        # state is None — no game init received yet
        msg = self._make_message(sender='agent-2')
        await service_with_persona._on_message(
            'message.all', msg.model_dump_json().encode()
        )
        # No exception, state stays None
        assert service_with_persona._state is None, 'state must remain None'

    @pytest.mark.asyncio
    async def test_invalid_body_does_not_raise(
        self, service_with_persona: AgentService
    ) -> None:
        """Test malformed message body is handled gracefully."""
        await service_with_persona._on_message('message.all', b'garbage')


class TestOnGameState:
    """Test AgentService._on_game_state"""

    @pytest.mark.asyncio
    async def test_agent_marked_eliminated(
        self, service_with_persona: AgentService
    ) -> None:
        """Test status becomes ELIMINATED when agent appears in eliminated list."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        gs = game_state(eliminated=['agent-1'], alive=['agent-2', 'agent-3'])
        await service_with_persona._on_game_state(
            'game.state', gs.model_dump_json().encode()
        )

        assert service_with_persona._status == AgentStatus.ELIMINATED, (
            'status must be ELIMINATED after appearing in eliminated list'
        )

    @pytest.mark.asyncio
    async def test_agent_stays_alive_when_not_eliminated(
        self, service_with_persona: AgentService
    ) -> None:
        """Test status stays ALIVE when agent is not in eliminated list."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        gs = game_state(eliminated=['agent-2'], alive=['agent-1', 'agent-3'])
        await service_with_persona._on_game_state(
            'game.state', gs.model_dump_json().encode()
        )

        assert service_with_persona._status == AgentStatus.ALIVE, (
            'status must remain ALIVE when agent is not in eliminated list'
        )

    @pytest.mark.asyncio
    async def test_game_state_stored(self, service_with_persona: AgentService) -> None:
        """Test latest game state is stored for use in turn/vote generation."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        gs = game_state(phase=GamePhase.DAY, round=3)
        await service_with_persona._on_game_state(
            'game.state', gs.model_dump_json().encode()
        )

        assert service_with_persona._current_game_state is not None, (
            'game state must be cached'
        )
        assert service_with_persona._current_game_state.round == 3, (
            'cached round must match received state'
        )

    @pytest.mark.asyncio
    async def test_citizen_does_not_vote_on_night_vote(
        self, service_with_persona: AgentService
    ) -> None:
        """Test CITIZEN agent does not publish a vote on NIGHT_VOTE phase."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        gs = game_state(phase=GamePhase.NIGHT_VOTE)
        await service_with_persona._on_game_state(
            'game.state', gs.model_dump_json().encode()
        )

        service_with_persona._messaging.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_body_does_not_raise(
        self, service_with_persona: AgentService
    ) -> None:
        """Test malformed game.state body is handled gracefully."""
        await service_with_persona._on_game_state('game.state', b'bad-json')


class TestOnTurn:
    """Test AgentService._on_turn"""

    @pytest.mark.asyncio
    async def test_citizen_publishes_to_message_all_during_day(
        self, service_with_persona: AgentService
    ) -> None:
        """Test CITIZEN publishes to message.all on a DAY turn."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        service_with_persona._http_client = AsyncMock()
        service_with_persona._http_client.post = AsyncMock(
            return_value=MagicMock(
                json=MagicMock(return_value={'text': 'I think agent-2 is suspicious.'}),
                raise_for_status=MagicMock(),
            )
        )

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        service_with_persona._current_game_state = game_state(phase=GamePhase.DAY)

        await service_with_persona._on_turn('game.turn.agent-1', b'')

        call_args = service_with_persona._messaging.publish.call_args
        assert call_args[0][0] == 'message.all', (
            'CITIZEN must publish to message.all during DAY phase'
        )

    @pytest.mark.asyncio
    async def test_mafia_publishes_to_message_mafia_during_night(
        self, service_with_persona: AgentService
    ) -> None:
        """Test MAFIA publishes to message.mafia on a NIGHT turn."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        service_with_persona._http_client = AsyncMock()
        service_with_persona._http_client.post = AsyncMock(
            return_value=MagicMock(
                json=MagicMock(return_value={'text': 'Let us eliminate agent-3.'}),
                raise_for_status=MagicMock(),
            )
        )

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.MAFIA)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        service_with_persona._current_game_state = game_state(phase=GamePhase.NIGHT)

        await service_with_persona._on_turn('game.turn.agent-1', b'')

        call_args = service_with_persona._messaging.publish.call_args
        assert call_args[0][0] == 'message.mafia', (
            'MAFIA must publish to message.mafia during NIGHT phase'
        )

    @pytest.mark.asyncio
    async def test_citizen_does_not_speak_during_night(
        self, service_with_persona: AgentService
    ) -> None:
        """Test CITIZEN skips publishing when phase is NIGHT."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        service_with_persona._http_client = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        service_with_persona._current_game_state = game_state(phase=GamePhase.NIGHT)

        await service_with_persona._on_turn('game.turn.agent-1', b'')

        service_with_persona._messaging.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_eliminated_agent_does_not_speak(
        self, service_with_persona: AgentService
    ) -> None:
        """Test eliminated agent skips the turn without publishing anything."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)
        service_with_persona._status = AgentStatus.ELIMINATED

        await service_with_persona._on_turn('game.turn.agent-1', b'')

        service_with_persona._messaging.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_message_added_to_history_after_turn(
        self, service_with_persona: AgentService
    ) -> None:
        """Test the published message is stored in local history."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        service_with_persona._http_client = AsyncMock()
        service_with_persona._http_client.post = AsyncMock(
            return_value=MagicMock(
                json=MagicMock(return_value={'text': 'My thoughts.'}),
                raise_for_status=MagicMock(),
            )
        )

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)
        service_with_persona._current_game_state = game_state(phase=GamePhase.DAY)

        await service_with_persona._on_turn('game.turn.agent-1', b'')

        assert service_with_persona._state is not None
        assert len(service_with_persona._state.message_history) == 1, (
            'published message must be appended to history'
        )
        assert service_with_persona._state.message_history[0].sender_id == 'agent-1', (
            'message in history must have agent sender_id'
        )


class TestOnHostQuestion:
    """Test AgentService._on_host_question"""

    @pytest.mark.asyncio
    async def test_answer_published_to_host_answer_routing_key(
        self, service_with_persona: AgentService
    ) -> None:
        """Test AgentAnswer is published to host.answer.{question_id}."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._messaging.publish = AsyncMock()
        service_with_persona._http_client = AsyncMock()
        service_with_persona._http_client.post = AsyncMock(
            return_value=MagicMock(
                json=MagicMock(return_value={'text': 'I am innocent!'}),
                raise_for_status=MagicMock(),
            )
        )

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        question = HostQuestion(
            question_id='q-123',
            target_agent_id='agent-1',
            question_text='Are you the mafia?',
        )
        await service_with_persona._on_host_question(
            'host.question.agent-1', question.model_dump_json().encode()
        )

        publish_routing_key = service_with_persona._messaging.publish.call_args[0][0]
        assert publish_routing_key == 'host.answer.q-123', (
            'answer must be published to host.answer.{question_id}'
        )

    @pytest.mark.asyncio
    async def test_invalid_question_body_does_not_raise(
        self, service_with_persona: AgentService
    ) -> None:
        """Test malformed host question body is handled gracefully."""
        service_with_persona._messaging = MagicMock()
        await service_with_persona._on_host_question(
            'host.question.agent-1', b'bad-json'
        )


class TestBuildLLMContext:
    """Test AgentService._generate_llm_response message history mapping"""

    @pytest.mark.asyncio
    async def test_own_messages_mapped_to_assistant_role(
        self, service_with_persona: AgentService
    ) -> None:
        """Test messages sent by this agent use assistant role in LLM context."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._http_client = AsyncMock()

        captured_payload: dict = {}

        async def fake_post(url: str, json: dict) -> MagicMock:
            captured_payload.update(json)
            mock = MagicMock()
            mock.json.return_value = {'text': 'ok'}
            mock.raise_for_status = MagicMock()
            return mock

        service_with_persona._http_client.post = fake_post

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        assert service_with_persona._state is not None
        own_msg = Message(
            sender_id='agent-1',
            content='I said this.',
            phase=GamePhase.DAY,
            round=1,
            target_audience=TargetAudience.ALL,
        )
        service_with_persona._state.message_history.append(own_msg)

        await service_with_persona._generate_llm_response('Your turn.', 256)

        history = captured_payload.get('messages', [])
        own_in_history = [m for m in history if m.get('content') == 'I said this.']
        assert len(own_in_history) == 1, (
            'own message must appear in LLM context exactly once'
        )
        assert own_in_history[0]['role'] == 'assistant', (
            "own messages must be mapped to 'assistant' role in LLM context"
        )

    @pytest.mark.asyncio
    async def test_other_messages_mapped_to_user_role_with_prefix(
        self, service_with_persona: AgentService
    ) -> None:
        """Test messages from other agents use user role with sender prefix."""
        service_with_persona._messaging = MagicMock()
        service_with_persona._messaging.subscribe = AsyncMock()
        service_with_persona._http_client = AsyncMock()

        captured_payload: dict = {}

        async def fake_post(url: str, json: dict) -> MagicMock:
            captured_payload.update(json)
            mock = MagicMock()
            mock.json.return_value = {'text': 'ok'}
            mock.raise_for_status = MagicMock()
            return mock

        service_with_persona._http_client.post = fake_post

        body = (
            AgentInit(agent_id='agent-1', role=AgentRole.CITIZEN)
            .model_dump_json()
            .encode()
        )
        await service_with_persona._on_game_init('game.init.agent-1', body)

        assert service_with_persona._state is not None
        other_msg = Message(
            sender_id='agent-2',
            content='You are suspicious.',
            phase=GamePhase.DAY,
            round=1,
            target_audience=TargetAudience.ALL,
        )
        service_with_persona._state.message_history.append(other_msg)

        await service_with_persona._generate_llm_response('Your turn.', 256)

        history = captured_payload.get('messages', [])
        other_in_history = [m for m in history if 'agent-2' in m.get('content', '')]
        assert len(other_in_history) == 1, (
            'other agent message must appear in LLM context'
        )
        assert other_in_history[0]['role'] == 'user', (
            "messages from other agents must use 'user' role"
        )
        assert '[agent-2]' in other_in_history[0]['content'], (
            'sender id must be prefixed in user message content'
        )
