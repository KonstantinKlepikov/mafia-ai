import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest
from _pytest.monkeypatch import MonkeyPatch

import services.game_service.core.service as svc_module
from services.game_service.config import GameServiceSettings
from services.game_service.core.service import GameService
from shared.models import (
    GamePhase,
    HostDecision,
    HostDecisionAction,
    Message,
    PersonaType,
    SystemPrompt,
    TargetAudience,
    VoteEvent,
)


def _make_settings(**kwargs: object) -> GameServiceSettings:
    defaults: dict[str, object] = dict(
        amqp_url='amqp://guest:guest@localhost/',
        llm_url='http://llm:8080',
        agent_count=4,
        mafia_count=1,
        phase_duration_seconds=10,
        vote_timeout_seconds=5,
        db_yaml_path='/app/config/prompts.yaml',
        message_max_tokens=150,
        vote_max_tokens=50,
    )
    defaults.update(kwargs)
    return GameServiceSettings(**defaults)  # type: ignore[arg-type]


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
def settings() -> GameServiceSettings:
    """GameServiceSettings for unit tests."""
    return _make_settings()


@pytest.fixture
def mock_messaging() -> AsyncMock:
    """Mocked MessagingClient."""
    return AsyncMock()


@pytest.fixture
def mock_database() -> AsyncMock:
    """Mocked Database with 4 personas."""
    m = AsyncMock()
    m.list_personas.return_value = [_make_persona(n) for n in range(1, 5)]
    m.get_persona.return_value = _make_persona(1)
    return m


@pytest.fixture
def mock_llm_client() -> httpx.AsyncClient:
    """Mocked httpx AsyncClient for LLM service."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = Mock()
    mock_response.json.return_value = {'text': 'Hello, I am a test agent!'}
    mock_response.raise_for_status = Mock()
    mock_client.post.return_value = mock_response
    return mock_client


@pytest.fixture
def svc(
    settings: GameServiceSettings,
    mock_messaging: AsyncMock,
    mock_database: AsyncMock,
    mock_llm_client: httpx.AsyncClient,
    monkeypatch: MonkeyPatch,
) -> GameService:
    """GameService with all external dependencies mocked."""
    monkeypatch.setattr(
        svc_module, 'MessagingClient', MagicMock(return_value=mock_messaging)
    )
    monkeypatch.setattr(svc_module, 'Database', MagicMock(return_value=mock_database))

    # Mock httpx.AsyncClient inside AgentManager
    def mock_async_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        return mock_llm_client

    monkeypatch.setattr(svc_module.httpx, 'AsyncClient', mock_async_client)
    return GameService(settings)


async def _cancel_task(task: asyncio.Task) -> None:  # type: ignore[type-arg]
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


class TestGameServiceInit:
    """Tests for GameService construction."""

    def test_initial_round_is_zero(self, svc: GameService) -> None:
        """Test round counter starts at 0 before any game begins."""
        assert svc._round == 0, f'expected round 0, got {svc._round}'

    def test_game_not_active_on_init(self, svc: GameService) -> None:
        """Test game loop is not active immediately after construction."""
        assert svc._game_active is False, '_game_active must be False on init'

    def test_game_task_is_none_on_init(self, svc: GameService) -> None:
        """Test no background task exists before begin_game is called."""
        assert svc._game_task is None, '_game_task must be None on init'

    def test_agent_manager_exists(self, svc: GameService) -> None:
        """Test GameService has an embedded AgentManager instance."""
        assert svc._agent_manager is not None, '_agent_manager must be set on init'


class TestGameServiceStart:
    """Tests for GameService.start."""

    async def test_start_connects_messaging(
        self, svc: GameService, mock_messaging: AsyncMock
    ) -> None:
        """Test start calls connect on the messaging client."""
        await svc.start()

        mock_messaging.connect.assert_called_once()

    async def test_start_subscribes_to_one_channel(
        self, svc: GameService, mock_messaging: AsyncMock
    ) -> None:
        """Test start registers vote RabbitMQ subscription."""
        await svc.start()

        assert mock_messaging.subscribe.call_count == 1, (
            f'expected 1 subscribe call, got {mock_messaging.subscribe.call_count}'
        )


class TestGameServiceStop:
    """Tests for GameService.stop."""

    async def test_stop_closes_messaging(
        self, svc: GameService, mock_messaging: AsyncMock
    ) -> None:
        """Test stop calls close on the messaging client."""
        await svc.stop()

        mock_messaging.close.assert_called_once()

    async def test_stop_closes_agent_manager(
        self, svc: GameService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test stop calls close on the agent manager."""
        mock_close = AsyncMock()
        monkeypatch.setattr(svc._agent_manager, 'close', mock_close)

        await svc.stop()

        mock_close.assert_called_once()

    async def test_stop_cancels_active_game_task(self, svc: GameService) -> None:
        """Test stop cancels a running game task."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        svc._game_task = mock_task

        await svc.stop()

        mock_task.cancel.assert_called_once()


class TestGameServiceBeginGame:
    """Tests for GameService.begin_game."""

    async def test_begin_game_raises_when_game_already_active(
        self, svc: GameService, monkeypatch: MonkeyPatch
    ) -> None:
        """Test begin_game raises RuntimeError if a game is running."""
        svc._game_active = True

        with pytest.raises(RuntimeError):
            await svc.begin_game()

    async def test_begin_game_calls_init_game(
        self, svc: GameService, monkeypatch: MonkeyPatch
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
        self, svc: GameService, monkeypatch: MonkeyPatch
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


class TestGameServiceGetGameState:
    """Tests for GameService.get_game_state."""

    def test_returns_current_state(self, svc: GameService) -> None:
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

    def test_returns_defensive_copy_of_alive_list(self, svc: GameService) -> None:
        """Test mutating the returned list does not affect internal state."""
        svc._alive = ['agent-1', 'agent-2']

        state = svc.get_game_state()
        state.alive_agents.append('agent-99')

        assert 'agent-99' not in svc._alive, (
            'mutating returned state must not affect _alive'
        )


class TestGameServiceSubmitHostDecision:
    """Tests for GameService.submit_host_decision."""

    def test_stores_the_decision(self, svc: GameService) -> None:
        """Test submit_host_decision stores the provided decision."""
        decision = HostDecision(action=HostDecisionAction.REJECT)

        svc.submit_host_decision(decision)

        assert svc._host_decision == decision, (
            f'expected {decision}, got {svc._host_decision}'
        )

    def test_sets_host_decision_event(self, svc: GameService) -> None:
        """Test submit_host_decision sets the synchronisation event."""
        decision = HostDecision(action=HostDecisionAction.APPROVE)

        svc.submit_host_decision(decision)

        assert svc._host_decision_event.is_set(), (
            '_host_decision_event must be set after submit'
        )


class TestGameServiceSubscribeMessages:
    """Tests for GameService.subscribe_messages."""

    async def test_replays_message_history(self, svc: GameService) -> None:
        """Test subscribe_messages yields existing messages before blocking."""
        msg = _make_message()
        svc._messages = [msg]

        gen = svc.subscribe_messages()
        result = await gen.__anext__()
        await gen.aclose()

        assert result == msg, f'expected {msg}, got {result}'

    async def test_streams_newly_arrived_messages(self, svc: GameService) -> None:
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


class TestGameServiceForceStopAgent:
    """Tests for GameService.force_stop_agent."""

    async def test_removes_agent_from_alive(
        self, svc: GameService, mock_messaging: AsyncMock
    ) -> None:
        """Test force_stop_agent eliminates the agent (removed from alive)."""
        svc._alive = ['agent-1', 'agent-2']
        svc._eliminated = []

        await svc.force_stop_agent('agent-1')

        assert 'agent-1' not in svc._alive, 'agent must be removed from alive'
        assert 'agent-1' in svc._eliminated, 'agent must be added to eliminated'
