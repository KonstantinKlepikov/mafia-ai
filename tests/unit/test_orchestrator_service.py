"""Unit tests for OrchestratorService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch

import services.orchestrator.core.service as svc_module
from services.orchestrator.config import OrchestratorSettings
from services.orchestrator.core.service import OrchestratorService
from shared.models import (
    AgentAnswer,
    AgentRole,
    GamePhase,
    HostDecision,
    HostDecisionAction,
    Message,
    PersonaType,
    SystemPrompt,
    TargetAudience,
    VoteEvent,
)


def _make_settings(**kwargs: object) -> OrchestratorSettings:
    defaults: dict[str, object] = dict(
        amqp_url='amqp://guest:guest@localhost/',
        vectordb_host='localhost',
        vectordb_port=8000,
        agent_count=4,
        mafia_count=1,
        phase_duration_seconds=10,
        vote_timeout_seconds=5,
        agent_http_port=8100,
        agent_host_pattern='agent-{n}',
    )
    defaults.update(kwargs)
    return OrchestratorSettings(**defaults)  # type: ignore[arg-type]


def _make_persona(n: int) -> SystemPrompt:
    return SystemPrompt(
        persona_id=f'persona-{n}',
        name=f'persona_{n}',
        persona_type=PersonaType.GOOD_NATURED,
        prompt='Test prompt.',
    )


def _make_message(
    sender_id: str = 'agent-1',
    content: str = 'Hello',
    phase: GamePhase = GamePhase.DAY,
    round_num: int = 1,
) -> Message:
    return Message(
        sender_id=sender_id,
        content=content,
        phase=phase,
        round=round_num,
        target_audience=TargetAudience.ALL,
    )


def _make_vote(
    voter_id: str = 'agent-1',
    target_id: str = 'agent-2',
    round_num: int = 1,
    phase: GamePhase = GamePhase.DAY_VOTE,
) -> VoteEvent:
    return VoteEvent(
        voter_id=voter_id,
        target_id=target_id,
        phase=phase,
        round=round_num,
    )


@pytest.fixture
def settings() -> OrchestratorSettings:
    """OrchestratorSettings for unit tests."""
    return _make_settings()


@pytest.fixture
def mock_messaging() -> AsyncMock:
    """Mocked MessagingClient."""
    return AsyncMock()


@pytest.fixture
def mock_vectordb() -> MagicMock:
    """Mocked VectorDBClient with 4 personas."""
    m = MagicMock()
    m.list_personas.return_value = [_make_persona(n) for n in range(1, 5)]
    return m


@pytest.fixture
def mock_poller() -> AsyncMock:
    """Mocked AgentPoller."""
    return AsyncMock()


@pytest.fixture
def svc(
    settings: OrchestratorSettings,
    mock_messaging: AsyncMock,
    mock_vectordb: MagicMock,
    mock_poller: AsyncMock,
    monkeypatch: MonkeyPatch,
) -> OrchestratorService:
    """OrchestratorService with all external dependencies mocked."""
    monkeypatch.setattr(
        svc_module, 'MessagingClient', MagicMock(return_value=mock_messaging)
    )
    monkeypatch.setattr(
        svc_module, 'VectorDBClient', MagicMock(return_value=mock_vectordb)
    )
    monkeypatch.setattr(svc_module, 'AgentPoller', MagicMock(return_value=mock_poller))
    return OrchestratorService(settings)


async def _cancel_task(task: asyncio.Task) -> None:  # type: ignore[type-arg]
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


class TestOrchestratorServiceInit:
    """Tests for OrchestratorService construction."""

    def test_initial_round_is_zero(self, svc: OrchestratorService) -> None:
        """Test round counter starts at 0 before any game begins."""
        assert svc._round == 0, f'expected round 0, got {svc._round}'

    def test_game_not_active_on_init(self, svc: OrchestratorService) -> None:
        """Test game loop is not active immediately after construction."""
        assert svc._game_active is False, '_game_active must be False on init'

    def test_game_task_is_none_on_init(self, svc: OrchestratorService) -> None:
        """Test no background task exists before begin_game is called."""
        assert svc._game_task is None, '_game_task must be None on init'


class TestOrchestratorServiceStart:
    """Tests for OrchestratorService.start."""

    async def test_start_connects_messaging(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test start calls connect on the messaging client."""
        await svc.start()

        mock_messaging.connect.assert_called_once()

    async def test_start_subscribes_to_three_channels(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test start registers three RabbitMQ subscriptions."""
        await svc.start()

        assert mock_messaging.subscribe.call_count == 3, (
            f'expected 3 subscribe calls, got {mock_messaging.subscribe.call_count}'
        )


class TestOrchestratorServiceStop:
    """Tests for OrchestratorService.stop."""

    async def test_stop_closes_messaging(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test stop calls close on the messaging client."""
        await svc.stop()

        mock_messaging.close.assert_called_once()

    async def test_stop_closes_poller(
        self, svc: OrchestratorService, mock_poller: AsyncMock
    ) -> None:
        """Test stop calls close on the agent poller."""
        await svc.stop()

        mock_poller.close.assert_called_once()

    async def test_stop_cancels_active_game_task(
        self, svc: OrchestratorService
    ) -> None:
        """Test stop cancels a running game task."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        svc._game_task = mock_task

        await svc.stop()

        mock_task.cancel.assert_called_once()


class TestOrchestratorServiceBeginGame:
    """Tests for OrchestratorService.begin_game."""

    async def test_begin_game_raises_when_game_already_active(
        self, svc: OrchestratorService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test begin_game raises RuntimeError if a game is running."""
        svc._game_active = True

        with pytest.raises(RuntimeError):
            await svc.begin_game()

    async def test_begin_game_calls_init_game(
        self, svc: OrchestratorService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test begin_game calls _init_game before starting the loop."""
        called: list[bool] = []

        async def mock_init() -> None:
            called.append(True)
            svc._game_active = True

        async def mock_loop() -> None:
            await asyncio.sleep(1000)

        monkeypatch.setattr(svc, '_init_game', mock_init)
        monkeypatch.setattr(svc, '_run_game_loop', mock_loop)

        await svc.begin_game()
        await _cancel_task(svc._game_task)  # type: ignore[arg-type]

        assert called, '_init_game must be called by begin_game'

    async def test_begin_game_creates_background_task(
        self, svc: OrchestratorService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test begin_game creates a game loop background task."""

        async def mock_init() -> None:
            svc._game_active = True

        async def mock_loop() -> None:
            await asyncio.sleep(1000)

        monkeypatch.setattr(svc, '_init_game', mock_init)
        monkeypatch.setattr(svc, '_run_game_loop', mock_loop)

        await svc.begin_game()
        assert svc._game_task is not None, '_game_task must be set after begin_game'
        await _cancel_task(svc._game_task)


class TestOrchestratorServiceGetGameState:
    """Tests for OrchestratorService.get_game_state."""

    def test_returns_current_state(self, svc: OrchestratorService) -> None:
        """Test get_game_state reflects current round, phase, alive, eliminated."""
        svc._round = 3
        svc._phase = GamePhase.DAY
        svc._alive = ['agent-1', 'agent-2']
        svc._eliminated = ['agent-3']

        state = svc.get_game_state()

        assert state.round == 3
        assert state.phase == GamePhase.DAY
        assert state.alive_agents == ['agent-1', 'agent-2']
        assert state.eliminated == ['agent-3']

    def test_returns_defensive_copy_of_alive_list(
        self, svc: OrchestratorService
    ) -> None:
        """Test mutating the returned list does not affect internal state."""
        svc._alive = ['agent-1', 'agent-2']

        state = svc.get_game_state()
        state.alive_agents.append('agent-99')

        assert 'agent-99' not in svc._alive, (
            'mutating returned state must not affect _alive'
        )


class TestOrchestratorServiceSubmitHostDecision:
    """Tests for OrchestratorService.submit_host_decision."""

    def test_stores_the_decision(self, svc: OrchestratorService) -> None:
        """Test submit_host_decision stores the provided decision."""
        decision = HostDecision(action=HostDecisionAction.REJECT)

        svc.submit_host_decision(decision)

        assert svc._host_decision == decision, (
            f'expected {decision}, got {svc._host_decision}'
        )

    def test_sets_host_decision_event(self, svc: OrchestratorService) -> None:
        """Test submit_host_decision sets the synchronisation event."""
        decision = HostDecision(action=HostDecisionAction.APPROVE)

        svc.submit_host_decision(decision)

        assert svc._host_decision_event.is_set(), (
            '_host_decision_event must be set after submit'
        )


class TestOrchestratorServiceSubscribeMessages:
    """Tests for OrchestratorService.subscribe_messages."""

    async def test_replays_message_history(self, svc: OrchestratorService) -> None:
        """Test subscribe_messages yields existing messages before blocking."""
        msg = _make_message()
        svc._messages = [msg]

        gen = svc.subscribe_messages()
        result = await gen.__anext__()
        await gen.aclose()

        assert result == msg, f'expected {msg}, got {result}'

    async def test_streams_newly_arrived_messages(
        self, svc: OrchestratorService
    ) -> None:
        """Test subscribe_messages yields messages put into the queue after start."""
        msg = _make_message(content='live')
        svc._messages = []

        async def inject() -> None:
            await asyncio.sleep(0)
            for q in list(svc._message_queues):
                await q.put(msg)

        task = asyncio.create_task(inject())
        gen = svc.subscribe_messages()
        result = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        await task
        await gen.aclose()

        assert result == msg, f'expected {msg}, got {result}'


class TestOrchestratorServiceGetAgentInfo:
    """Tests for get_agents_info and get_agent_info."""

    async def test_get_agents_info_delegates_to_poller(
        self, svc: OrchestratorService, mock_poller: AsyncMock
    ) -> None:
        """Test get_agents_info calls poll_all with the current alive list."""
        svc._alive = ['agent-1', 'agent-2']
        mock_poller.poll_all.return_value = {}

        await svc.get_agents_info()

        mock_poller.poll_all.assert_called_once_with(['agent-1', 'agent-2'])

    async def test_get_agent_info_delegates_to_poller(
        self, svc: OrchestratorService, mock_poller: AsyncMock
    ) -> None:
        """Test get_agent_info calls poll_agent with the given agent_id."""
        mock_poller.poll_agent.return_value = None

        await svc.get_agent_info('agent-3')

        mock_poller.poll_agent.assert_called_once_with('agent-3')


class TestOrchestratorServiceAskAgent:
    """Tests for OrchestratorService.ask_agent."""

    async def test_publishes_host_question_with_correct_routing_key(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test ask_agent publishes HostQuestion to host.question.{agent_id}."""
        await svc.ask_agent('agent-2', 'qid-1', 'What did you see?')

        routing_key = mock_messaging.publish.call_args[0][0]
        assert routing_key == 'host.question.agent-2', (
            f'wrong routing key: {routing_key}'
        )


class TestOrchestratorServiceGetAgentAnswer:
    """Tests for OrchestratorService.get_agent_answer."""

    async def test_returns_cached_answer_and_clears_cache(
        self, svc: OrchestratorService
    ) -> None:
        """Test get_agent_answer returns cached value without blocking."""
        svc._answer_cache['qid-1'] = 'cached answer'

        result = await svc.get_agent_answer('qid-1', timeout=1.0)

        assert result == 'cached answer', f'expected cached answer, got {result}'
        assert 'qid-1' not in svc._answer_cache, 'cache must be cleared after pop'

    async def test_waits_for_future_result(self, svc: OrchestratorService) -> None:
        """Test get_agent_answer blocks until a future is resolved."""
        qid = 'qid-2'

        async def resolve() -> None:
            await asyncio.sleep(0)
            fut = svc._pending_answers.get(qid)
            if fut and not fut.done():
                fut.set_result('future answer')

        task = asyncio.create_task(resolve())
        result = await svc.get_agent_answer(qid, timeout=1.0)
        await task

        assert result == 'future answer', f'expected future answer, got {result}'

    async def test_returns_none_on_timeout(self, svc: OrchestratorService) -> None:
        """Test get_agent_answer returns None when no answer arrives in time."""
        result = await svc.get_agent_answer('qid-missing', timeout=0.01)

        assert result is None, f'expected None on timeout, got {result}'


class TestOrchestratorServiceForceStopAgent:
    """Tests for OrchestratorService.force_stop_agent."""

    async def test_removes_agent_from_alive(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test force_stop_agent eliminates the agent (removed from alive)."""
        svc._alive = ['agent-1', 'agent-2']
        svc._eliminated = []

        await svc.force_stop_agent('agent-1')

        assert 'agent-1' not in svc._alive, 'agent-1 must be removed from alive'
        assert 'agent-1' in svc._eliminated, 'agent-1 must appear in eliminated'


class TestOrchestratorServiceInitGame:
    """Tests for OrchestratorService._init_game."""

    async def test_resets_round_to_one(self, svc: OrchestratorService) -> None:
        """Test _init_game sets round to 1."""
        svc._round = 5

        await svc._init_game()

        assert svc._round == 1, f'expected round 1 after init, got {svc._round}'

    async def test_alive_list_contains_all_agents(
        self, svc: OrchestratorService
    ) -> None:
        """Test _init_game populates alive with agent_count agents."""
        await svc._init_game()

        assert len(svc._alive) == svc._settings.agent_count, (
            f'expected {svc._settings.agent_count} alive, got {len(svc._alive)}'
        )

    async def test_assigns_correct_mafia_count(self, svc: OrchestratorService) -> None:
        """Test _init_game assigns exactly mafia_count MAFIA roles."""
        await svc._init_game()

        mafia = [aid for aid, role in svc._roles.items() if role == AgentRole.MAFIA]
        assert len(mafia) == svc._settings.mafia_count, (
            f'expected {svc._settings.mafia_count} mafia, got {len(mafia)}'
        )

    async def test_publishes_agent_init_for_each_agent(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test _init_game publishes an AgentInit message for every agent."""
        await svc._init_game()

        assert mock_messaging.publish.call_count == svc._settings.agent_count, (
            f'expected {svc._settings.agent_count} publish calls, '
            f'got {mock_messaging.publish.call_count}'
        )

    async def test_sets_game_active(self, svc: OrchestratorService) -> None:
        """Test _init_game sets _game_active to True."""
        await svc._init_game()

        assert svc._game_active is True, '_game_active must be True after _init_game'


class TestOrchestratorServiceWaitForHostDecision:
    """Tests for OrchestratorService._wait_for_host_decision."""

    async def _submit_decision(
        self, svc: OrchestratorService, decision: HostDecision
    ) -> None:
        """Yield control so _wait_for_host_decision reaches event.wait(),
        then submit."""
        await asyncio.sleep(0)
        svc.submit_host_decision(decision)

    async def test_approve_resolves_via_vote_majority(
        self, svc: OrchestratorService
    ) -> None:
        """Test APPROVE action returns the agent with majority votes."""
        svc._round = 1
        votes = [
            _make_vote('agent-2', 'agent-1'),
            _make_vote('agent-3', 'agent-1'),
            _make_vote('agent-4', 'agent-1'),
        ]
        decision = HostDecision(action=HostDecisionAction.APPROVE)

        task = asyncio.create_task(self._submit_decision(svc, decision))
        result = await svc._wait_for_host_decision(votes)
        await task

        assert result == 'agent-1', f'APPROVE must return majority target, got {result}'

    async def test_reject_returns_none(self, svc: OrchestratorService) -> None:
        """Test REJECT action returns None (no elimination)."""
        decision = HostDecision(action=HostDecisionAction.REJECT)

        task = asyncio.create_task(self._submit_decision(svc, decision))
        result = await svc._wait_for_host_decision([])
        await task

        assert result is None, f'REJECT must return None, got {result}'

    async def test_override_returns_specified_target(
        self, svc: OrchestratorService
    ) -> None:
        """Test OVERRIDE action returns the explicitly provided target_id."""
        decision = HostDecision(action=HostDecisionAction.OVERRIDE, target_id='agent-3')

        task = asyncio.create_task(self._submit_decision(svc, decision))
        result = await svc._wait_for_host_decision([])
        await task

        assert result == 'agent-3', f'OVERRIDE must return target_id, got {result}'


class TestOrchestratorServiceEliminateAgent:
    """Tests for OrchestratorService._eliminate_agent."""

    async def test_removes_agent_from_alive(self, svc: OrchestratorService) -> None:
        """Test _eliminate_agent removes the agent from _alive."""
        svc._alive = ['agent-1', 'agent-2']

        await svc._eliminate_agent('agent-1')

        assert 'agent-1' not in svc._alive, (
            'agent-1 must not be in alive after eliminate'
        )

    async def test_adds_agent_to_eliminated(self, svc: OrchestratorService) -> None:
        """Test _eliminate_agent appends the agent to _eliminated."""
        svc._alive = ['agent-1']
        svc._eliminated = []

        await svc._eliminate_agent('agent-1')

        assert 'agent-1' in svc._eliminated, (
            'agent-1 must appear in eliminated after eliminate'
        )

    async def test_publishes_elimination_game_state(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test _eliminate_agent publishes to the agent's elimination routing key."""
        svc._alive = ['agent-1']

        await svc._eliminate_agent('agent-1')

        routing_key = mock_messaging.publish.call_args[0][0]
        assert routing_key == 'game.state.eliminated.agent-1', (
            f'wrong routing key: {routing_key}'
        )

    async def test_stops_agent_container(
        self, svc: OrchestratorService, mock_poller: AsyncMock
    ) -> None:
        """Test _eliminate_agent calls stop_container on the poller."""
        svc._alive = ['agent-2']

        await svc._eliminate_agent('agent-2')

        mock_poller.stop_container.assert_called_once_with('agent-2')

    async def test_skips_agent_not_in_alive(
        self, svc: OrchestratorService, mock_messaging: AsyncMock
    ) -> None:
        """Test _eliminate_agent is a no-op for agents not in the alive list."""
        svc._alive = ['agent-2']
        svc._eliminated = []

        await svc._eliminate_agent('agent-99')

        mock_messaging.publish.assert_not_called()
        assert 'agent-99' not in svc._eliminated, (
            'agent-99 must not appear in eliminated'
        )


class TestOrchestratorServiceCheckAndHandleWin:
    """Tests for OrchestratorService._check_and_handle_win."""

    def test_citizens_win_when_all_mafia_eliminated(
        self, svc: OrchestratorService
    ) -> None:
        """Test returns True and sets GAME_OVER when no mafia agents remain."""
        svc._alive = ['agent-1', 'agent-2']
        svc._roles = {
            'agent-1': AgentRole.CITIZEN,
            'agent-2': AgentRole.CITIZEN,
        }

        result = svc._check_and_handle_win()

        assert result is True, 'must return True when mafia is eliminated'
        assert svc._phase == GamePhase.GAME_OVER, (
            f'phase must be GAME_OVER, got {svc._phase}'
        )

    def test_mafia_wins_when_citizens_are_outnumbered(
        self, svc: OrchestratorService
    ) -> None:
        """Test returns True and sets GAME_OVER when citizens <= mafia."""
        svc._alive = ['agent-1', 'agent-2']
        svc._roles = {
            'agent-1': AgentRole.MAFIA,
            'agent-2': AgentRole.CITIZEN,
        }

        result = svc._check_and_handle_win()

        assert result is True, 'must return True when mafia wins'
        assert svc._game_active is False, '_game_active must be False'

    def test_returns_false_when_game_should_continue(
        self, svc: OrchestratorService
    ) -> None:
        """Test returns False when win condition is not yet met."""
        svc._alive = ['agent-1', 'agent-2', 'agent-3']
        svc._roles = {
            'agent-1': AgentRole.MAFIA,
            'agent-2': AgentRole.CITIZEN,
            'agent-3': AgentRole.CITIZEN,
        }

        result = svc._check_and_handle_win()

        assert result is False, 'must return False when game continues'
        assert svc._phase != GamePhase.GAME_OVER, 'phase must not be GAME_OVER'


class TestOrchestratorServiceOnMessage:
    """Tests for OrchestratorService._on_message."""

    async def test_appends_message_to_history(self, svc: OrchestratorService) -> None:
        """Test _on_message stores received message in _messages."""
        msg = _make_message()
        body = msg.model_dump_json().encode()

        await svc._on_message('message.agent-1', body)

        assert msg in svc._messages, 'message must be appended to _messages'

    async def test_notifies_sse_queues(self, svc: OrchestratorService) -> None:
        """Test _on_message puts message into every registered SSE queue."""
        msg = _make_message()
        body = msg.model_dump_json().encode()
        queue: asyncio.Queue[Message] = asyncio.Queue()
        svc._message_queues.append(queue)

        await svc._on_message('message.agent-1', body)

        assert not queue.empty(), 'SSE queue must receive the message'
        received = queue.get_nowait()
        assert received == msg, f'expected {msg}, got {received}'

    async def test_signals_turn_complete_for_sender(
        self, svc: OrchestratorService
    ) -> None:
        """Test _on_message triggers the sender's turn completion event."""
        event = asyncio.Event()
        svc._turn_events['agent-1'] = event
        msg = _make_message(sender_id='agent-1')
        body = msg.model_dump_json().encode()

        await svc._on_message('message.agent-1', body)

        assert event.is_set(), 'turn event for sender must be set'

    async def test_ignores_invalid_json_body(self, svc: OrchestratorService) -> None:
        """Test _on_message does not raise on malformed message body."""
        await svc._on_message('message.agent-1', b'not json')  # must not raise
        assert svc._messages == [], 'nothing must be added to _messages on error'


class TestOrchestratorServiceOnVote:
    """Tests for OrchestratorService._on_vote."""

    async def test_enqueues_vote(self, svc: OrchestratorService) -> None:
        """Test _on_vote puts the parsed VoteEvent into _vote_queue."""
        vote = _make_vote()
        body = vote.model_dump_json().encode()

        await svc._on_vote('vote.agent-1', body)

        assert not svc._vote_queue.empty(), '_vote_queue must contain the vote'
        received = svc._vote_queue.get_nowait()
        assert received == vote, f'expected {vote}, got {received}'

    async def test_ignores_invalid_json_body(self, svc: OrchestratorService) -> None:
        """Test _on_vote does not raise on malformed body."""
        await svc._on_vote('vote.agent-1', b'bad data')  # must not raise
        assert svc._vote_queue.empty(), 'nothing must be queued on parse error'


class TestOrchestratorServiceOnHostAnswer:
    """Tests for OrchestratorService._on_host_answer."""

    async def test_resolves_pending_future(self, svc: OrchestratorService) -> None:
        """Test _on_host_answer sets the result on a waiting future."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        svc._pending_answers['qid-7'] = fut

        answer = AgentAnswer(
            question_id='qid-7', agent_id='agent-1', answer_text='Yes.'
        )
        await svc._on_host_answer(
            'host.answer.qid-7', answer.model_dump_json().encode()
        )

        assert fut.done(), 'future must be resolved'
        assert fut.result() == 'Yes.', f'expected "Yes.", got {fut.result()}'

    async def test_caches_answer_when_no_future_waiting(
        self, svc: OrchestratorService
    ) -> None:
        """Test _on_host_answer caches the answer if no future is registered."""
        answer = AgentAnswer(question_id='qid-8', agent_id='agent-2', answer_text='No.')
        await svc._on_host_answer(
            'host.answer.qid-8', answer.model_dump_json().encode()
        )

        assert svc._answer_cache.get('qid-8') == 'No.', (
            'answer must be cached when no future is waiting'
        )

    async def test_ignores_invalid_json_body(self, svc: OrchestratorService) -> None:
        """Test _on_host_answer does not raise on malformed body."""
        await svc._on_host_answer('host.answer.x', b'garbage')  # must not raise


class TestOrchestratorServiceSignalTurnComplete:
    """Tests for OrchestratorService._signal_turn_complete."""

    def test_sets_existing_turn_event(self, svc: OrchestratorService) -> None:
        """Test _signal_turn_complete sets the event for the given agent."""
        event = asyncio.Event()
        svc._turn_events['agent-3'] = event

        svc._signal_turn_complete('agent-3')

        assert event.is_set(), 'turn event must be set for agent-3'

    def test_noop_when_no_event_registered(self, svc: OrchestratorService) -> None:
        """Test _signal_turn_complete does not raise if agent has no turn event."""
        svc._signal_turn_complete('agent-99')  # must not raise


class TestOrchestratorServiceDrainVoteQueue:
    """Tests for OrchestratorService._drain_vote_queue."""

    async def test_empties_non_empty_queue(self, svc: OrchestratorService) -> None:
        """Test _drain_vote_queue removes all items from _vote_queue."""
        await svc._vote_queue.put(_make_vote())
        await svc._vote_queue.put(_make_vote(voter_id='agent-2'))

        svc._drain_vote_queue()

        assert svc._vote_queue.empty(), 'queue must be empty after drain'

    def test_does_not_raise_on_empty_queue(self, svc: OrchestratorService) -> None:
        """Test _drain_vote_queue is a no-op on an already-empty queue."""
        svc._drain_vote_queue()  # must not raise


class TestOrchestratorServiceCollectVotes:
    """Tests for OrchestratorService._collect_votes."""

    async def test_returns_votes_for_current_round(
        self, svc: OrchestratorService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test _collect_votes returns exactly the votes matching current round."""
        svc._round = 1
        v1 = _make_vote(voter_id='agent-1', round_num=1)
        v2 = _make_vote(voter_id='agent-2', round_num=1)

        monkeypatch.setattr(svc, '_drain_vote_queue', lambda: None)
        await svc._vote_queue.put(v1)
        await svc._vote_queue.put(v2)

        result = await svc._collect_votes(2, 'test')

        assert result == [v1, v2], f'expected [v1, v2], got {result}'

    async def test_discards_stale_round_votes(
        self, svc: OrchestratorService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test _collect_votes silently drops votes from a previous round."""
        svc._round = 2
        stale = _make_vote(round_num=1)
        valid = _make_vote(round_num=2)

        monkeypatch.setattr(svc, '_drain_vote_queue', lambda: None)
        await svc._vote_queue.put(stale)
        await svc._vote_queue.put(valid)

        result = await svc._collect_votes(1, 'test')

        assert len(result) == 1, f'expected 1 vote, got {len(result)}'
        assert result[0].round == 2, 'stale vote must be discarded'

    async def test_drains_queue_before_collecting(
        self, svc: OrchestratorService
    ) -> None:
        """Test _collect_votes clears stale votes from queue before starting."""
        old_vote = _make_vote(round_num=0)
        await svc._vote_queue.put(old_vote)

        result = await svc._collect_votes(0, 'test')

        assert result == [], f'expected [], got {result}'
        assert svc._vote_queue.empty(), 'queue must be empty after drain'


class TestOrchestratorServiceMafiaAlive:
    """Tests for OrchestratorService._mafia_alive."""

    def test_returns_only_mafia_agents(self, svc: OrchestratorService) -> None:
        """Test _mafia_alive filters out citizen agents."""
        svc._alive = ['agent-1', 'agent-2', 'agent-3']
        svc._roles = {
            'agent-1': AgentRole.MAFIA,
            'agent-2': AgentRole.CITIZEN,
            'agent-3': AgentRole.MAFIA,
        }

        result = svc._mafia_alive()

        assert result == ['agent-1', 'agent-3'], (
            f'expected only mafia agents, got {result}'
        )

    def test_returns_empty_when_no_mafia_alive(self, svc: OrchestratorService) -> None:
        """Test _mafia_alive returns [] when all mafia are eliminated."""
        svc._alive = ['agent-2']
        svc._roles = {'agent-2': AgentRole.CITIZEN}

        result = svc._mafia_alive()

        assert result == [], f'expected empty list, got {result}'


class TestOrchestratorServiceRunSpeakPhase:
    """Tests for OrchestratorService._run_speak_phase."""

    async def test_publishes_turn_signal_for_each_alive_agent(
        self, svc: OrchestratorService
    ) -> None:
        """Test _run_speak_phase publishes one TurnSignal per alive agent."""
        svc._alive = ['agent-1', 'agent-2']
        svc._roles = {
            'agent-1': AgentRole.CITIZEN,
            'agent-2': AgentRole.CITIZEN,
        }
        svc._phase = GamePhase.DAY
        svc._round = 1

        async def mock_publish(routing_key: str, *args: object) -> None:
            if routing_key.startswith('game.turn.'):
                agent_id = routing_key.split('.')[-1]
                ev = svc._turn_events.get(agent_id)
                if ev:
                    ev.set()

        svc._messaging.publish.side_effect = mock_publish  # type: ignore[attr-defined]

        await svc._run_speak_phase(mafia_only=False)

        assert svc._messaging.publish.call_count == 2, (  # type: ignore[attr-defined]
            'expected 2 turn signals'
        )

    async def test_sends_turn_signal_only_to_mafia_when_mafia_only(
        self, svc: OrchestratorService
    ) -> None:
        """Test _run_speak_phase sends signals only to mafia during night phase."""
        svc._alive = ['agent-1', 'agent-2', 'agent-3']
        svc._roles = {
            'agent-1': AgentRole.MAFIA,
            'agent-2': AgentRole.CITIZEN,
            'agent-3': AgentRole.CITIZEN,
        }
        svc._phase = GamePhase.NIGHT
        svc._round = 1
        published: list[str] = []

        async def mock_publish(routing_key: str, *args: object) -> None:
            published.append(routing_key)
            if routing_key.startswith('game.turn.'):
                agent_id = routing_key.split('.')[-1]
                ev = svc._turn_events.get(agent_id)
                if ev:
                    ev.set()

        svc._messaging.publish.side_effect = mock_publish  # type: ignore[attr-defined]

        await svc._run_speak_phase(mafia_only=True)

        turn_keys = [k for k in published if k.startswith('game.turn.')]
        assert len(turn_keys) == 1, (
            f'only mafia agent must get a turn signal, got {turn_keys}'
        )
        assert 'game.turn.agent-1' in turn_keys, (
            f'mafia agent-1 must receive the turn signal, got {turn_keys}'
        )

    async def test_skips_when_no_targets(self, svc: OrchestratorService) -> None:
        """Test _run_speak_phase does nothing when target list is empty."""
        svc._alive = []
        svc._roles = {}

        await svc._run_speak_phase(mafia_only=False)

        svc._messaging.publish.assert_not_called()  # type: ignore[attr-defined]
