"""Unit tests for the orchestrator REST API endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from shared.models import (
    AgentInfo,
    AgentRole,
    AgentStatus,
    GamePhase,
    GameState,
    HostDecisionAction,
)


def _make_game_state(**kwargs: object) -> GameState:
    defaults: dict[str, object] = dict(
        round=1,
        phase=GamePhase.DAY,
        alive_agents=['agent-1', 'agent-2'],
        eliminated=[],
    )
    defaults.update(kwargs)
    return GameState(**defaults)  # type: ignore[arg-type]


def _make_agent_info(**kwargs: object) -> AgentInfo:
    defaults: dict[str, object] = dict(
        agent_id='agent-1',
        persona_name='Test Persona',
        role=AgentRole.CITIZEN,
        status=AgentStatus.ALIVE,
    )
    defaults.update(kwargs)
    return AgentInfo(**defaults)  # type: ignore[arg-type]


class TestStartGame:
    """Tests for POST /game/start."""

    def test_returns_200_when_game_not_active(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/start returns 200 when no game is running."""
        response = orchestrator_client.post('/game/start')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_started_status(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/start response body contains status=started."""
        response = orchestrator_client.post('/game/start')

        assert response.json()['status'] == 'started', (
            f'expected status=started, got {response.json()}'
        )

    def test_returns_409_when_game_already_active(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test POST /game/start returns 409 when a game is already running."""
        mock_orchestrator_svc.begin_game.side_effect = RuntimeError('already active')

        response = orchestrator_client.post('/game/start')

        assert response.status_code == 409, f'expected 409, got {response.status_code}'


class TestGetGameState:
    """Tests for GET /game/state."""

    def test_returns_200(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test GET /game/state returns HTTP 200."""
        response = orchestrator_client.get('/game/state')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_round_field(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test GET /game/state response contains the correct round number."""
        mock_orchestrator_svc.get_game_state.return_value = _make_game_state(round=5)

        response = orchestrator_client.get('/game/state')

        assert response.json()['round'] == 5, f'wrong round: {response.json()["round"]}'

    def test_returns_phase_field(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test GET /game/state response contains the current phase."""
        mock_orchestrator_svc.get_game_state.return_value = _make_game_state(
            phase=GamePhase.NIGHT
        )

        response = orchestrator_client.get('/game/state')

        assert response.json()['phase'] == GamePhase.NIGHT, (
            f'wrong phase: {response.json()["phase"]}'
        )

    def test_returns_alive_agents(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test GET /game/state response contains alive_agents list."""
        mock_orchestrator_svc.get_game_state.return_value = _make_game_state(
            alive_agents=['agent-3', 'agent-4'],
        )

        response = orchestrator_client.get('/game/state')

        assert response.json()['alive_agents'] == ['agent-3', 'agent-4'], (
            f'wrong alive_agents: {response.json()["alive_agents"]}'
        )

    def test_returns_eliminated_agents(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test GET /game/state response contains eliminated list."""
        mock_orchestrator_svc.get_game_state.return_value = _make_game_state(
            eliminated=['agent-1'],
        )

        response = orchestrator_client.get('/game/state')

        assert response.json()['eliminated'] == ['agent-1'], (
            f'wrong eliminated: {response.json()["eliminated"]}'
        )


class TestHostDecision:
    """Tests for POST /game/host/decision."""

    def test_returns_200_on_approve(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/host/decision returns 200 for APPROVE action."""
        response = orchestrator_client.post(
            '/game/host/decision',
            json={'action': HostDecisionAction.APPROVE},
        )

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_200_on_reject(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/host/decision returns 200 for REJECT action."""
        response = orchestrator_client.post(
            '/game/host/decision',
            json={'action': HostDecisionAction.REJECT},
        )

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_200_on_override(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/host/decision returns 200 for OVERRIDE action."""
        response = orchestrator_client.post(
            '/game/host/decision',
            json={'action': HostDecisionAction.OVERRIDE, 'target_id': 'agent-2'},
        )

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_accepted_status(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/host/decision response body has status=accepted."""
        response = orchestrator_client.post(
            '/game/host/decision',
            json={'action': HostDecisionAction.APPROVE},
        )

        assert response.json()['status'] == 'accepted', (
            f'expected accepted, got {response.json()}'
        )

    def test_calls_submit_host_decision(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test POST /game/host/decision delegates to submit_host_decision."""
        orchestrator_client.post(
            '/game/host/decision',
            json={'action': HostDecisionAction.APPROVE},
        )

        mock_orchestrator_svc.submit_host_decision.assert_called_once()


class TestStreamMessages:
    """Tests for GET /game/messages."""

    def test_returns_200(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test GET /game/messages returns HTTP 200."""
        response = orchestrator_client.get('/game/messages')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_content_type_is_event_stream(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test GET /game/messages returns text/event-stream content type."""
        response = orchestrator_client.get('/game/messages')

        assert 'text/event-stream' in response.headers['content-type'], (
            f'expected text/event-stream, got {response.headers["content-type"]}'
        )


class TestGetAgents:
    """Tests for GET /game/agents."""

    def test_returns_200(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test GET /game/agents returns HTTP 200."""
        response = orchestrator_client.get('/game/agents')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_empty_dict_when_no_agents(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test GET /game/agents returns empty dict when no agents are alive."""
        response = orchestrator_client.get('/game/agents')

        assert response.json() == {}, f'expected empty dict, got {response.json()}'

    def test_returns_agent_info_by_id(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test GET /game/agents returns a map of agent_id to AgentInfo."""
        info = _make_agent_info(agent_id='agent-7')
        mock_orchestrator_svc.get_agents_info.return_value = {'agent-7': info}

        response = orchestrator_client.get('/game/agents')

        assert 'agent-7' in response.json(), (
            f'expected agent-7 in response, got {response.json()}'
        )


class TestGetAgent:
    """Tests for GET /game/agents/{agent_id}."""

    def test_returns_200_when_agent_found(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test returns 200 when agent is reachable."""
        mock_orchestrator_svc.get_agent_info.return_value = _make_agent_info()

        response = orchestrator_client.get('/game/agents/agent-1')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_correct_agent_id(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test response body contains the expected agent_id."""
        mock_orchestrator_svc.get_agent_info.return_value = _make_agent_info(
            agent_id='agent-5'
        )

        response = orchestrator_client.get('/game/agents/agent-5')

        assert response.json()['agent_id'] == 'agent-5', (
            f'wrong agent_id: {response.json()}'
        )

    def test_returns_404_when_agent_not_found(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test returns 404 when agent is unreachable or unknown."""
        response = orchestrator_client.get('/game/agents/unknown-agent')

        assert response.status_code == 404, f'expected 404, got {response.status_code}'


class TestAskAgent:
    """Tests for POST /game/agents/{agent_id}/question."""

    def test_returns_202(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test POST /game/agents/{agent_id}/question returns 202 Accepted."""
        response = orchestrator_client.post(
            '/game/agents/agent-1/question',
            json={'question_text': 'Are you mafia?'},
        )

        assert response.status_code == 202, f'expected 202, got {response.status_code}'

    def test_returns_question_id(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test response body contains a question_id UUID."""
        response = orchestrator_client.post(
            '/game/agents/agent-1/question',
            json={'question_text': 'Are you mafia?'},
        )

        assert 'question_id' in response.json(), (
            f'question_id missing in response: {response.json()}'
        )

    def test_calls_ask_agent_with_correct_args(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test ask_agent is called with the agent_id and question_text."""
        response = orchestrator_client.post(
            '/game/agents/agent-3/question',
            json={'question_text': 'Who did you vote for?'},
        )

        question_id = response.json()['question_id']
        mock_orchestrator_svc.ask_agent.assert_called_once_with(
            'agent-3', question_id, 'Who did you vote for?'
        )


class TestGetAgentAnswer:
    """Tests for GET /game/agents/{agent_id}/question/{question_id}."""

    def test_returns_200_with_answer(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test returns 200 and answer text when answer is available."""
        mock_orchestrator_svc.get_agent_answer.return_value = 'I am not mafia.'

        response = orchestrator_client.get('/game/agents/agent-1/question/q-123')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'
        assert response.json()['answer'] == 'I am not mafia.', (
            f'wrong answer: {response.json()}'
        )

    def test_returns_408_when_no_answer(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test returns 408 when answer is not received within timeout."""
        response = orchestrator_client.get('/game/agents/agent-1/question/q-timeout')

        assert response.status_code == 408, f'expected 408, got {response.status_code}'

    def test_calls_get_agent_answer_with_question_id(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test get_agent_answer is called with the correct question_id."""
        orchestrator_client.get('/game/agents/agent-1/question/q-xyz')

        call_args = mock_orchestrator_svc.get_agent_answer.call_args
        assert call_args[0][0] == 'q-xyz', f'wrong question_id passed: {call_args}'


class TestForceStopAgent:
    """Tests for DELETE /game/agents/{agent_id}."""

    def test_returns_200(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test DELETE /game/agents/{agent_id} returns HTTP 200."""
        response = orchestrator_client.delete('/game/agents/agent-1')

        assert response.status_code == 200, f'expected 200, got {response.status_code}'

    def test_returns_stopped_status(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test response body contains status=stopped."""
        response = orchestrator_client.delete('/game/agents/agent-1')

        assert response.json()['status'] == 'stopped', (
            f'wrong status: {response.json()}'
        )

    def test_returns_agent_id_in_body(
        self,
        orchestrator_client: TestClient,
    ) -> None:
        """Test response body contains the agent_id that was stopped."""
        response = orchestrator_client.delete('/game/agents/agent-2')

        assert response.json()['agent_id'] == 'agent-2', (
            f'wrong agent_id: {response.json()}'
        )

    def test_calls_force_stop_agent(
        self,
        orchestrator_client: TestClient,
        mock_orchestrator_svc: MagicMock,
    ) -> None:
        """Test DELETE /game/agents/{agent_id} delegates to force_stop_agent."""
        orchestrator_client.delete('/game/agents/agent-3')

        mock_orchestrator_svc.force_stop_agent.assert_called_once_with('agent-3')
