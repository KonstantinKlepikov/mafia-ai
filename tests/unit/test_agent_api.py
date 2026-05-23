"""Unit tests for the agent REST API (GET /agent/info)."""

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from services.agent.core.service import AgentService
from shared.models import AgentInfo, AgentRole, AgentStatus


def _make_info(**kwargs) -> AgentInfo:
    defaults = {
        'agent_id': 'agent-1',
        'persona_name': 'persona_1_good_natured',
        'role': AgentRole.CITIZEN,
        'status': AgentStatus.ALIVE,
    }
    defaults.update(kwargs)
    return AgentInfo(**defaults)


class TestGetAgentInfo:
    """Test GET /agent/info endpoint."""

    def test_returns_200(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test GET /agent/info returns HTTP 200."""

        info = _make_info()

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.status_code == 200, 'GET /agent/info must return 200'

    def test_returns_agent_id(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body contains the correct agent_id."""

        info = _make_info(agent_id='agent-5')

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.json()['agent_id'] == 'agent-5', (
            'agent_id in response must match the service value'
        )

    def test_returns_persona_name(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body contains the persona_name field."""

        info = _make_info(persona_name='persona_3_конспиролог')

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.json()['persona_name'] == 'persona_3_конспиролог', (
            'persona_name must be returned in response'
        )

    def test_returns_role(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body contains the correct role."""

        info = _make_info(role=AgentRole.MAFIA)

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.json()['role'] == 'MAFIA', 'role must match the service value'

    def test_returns_alive_status(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body contains ALIVE status when agent is alive."""

        info = _make_info(status=AgentStatus.ALIVE)

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.json()['status'] == 'ALIVE', (
            'status must be ALIVE when agent is alive'
        )

    def test_returns_eliminated_status(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body contains ELIMINATED status after elimination."""

        info = _make_info(status=AgentStatus.ELIMINATED)

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        response = agent_client.get('/agent/info')

        assert response.json()['status'] == 'ELIMINATED', (
            'status must be ELIMINATED after the agent is eliminated'
        )

    def test_response_schema_fields_present(
        self,
        agent_client: TestClient,
        agent_service: AgentService,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Test response body includes all required AgentInfo fields."""

        info = _make_info()

        def mock_get_info() -> AgentInfo:
            return info

        monkeypatch.setattr(agent_service, 'get_info', mock_get_info)

        data = agent_client.get('/agent/info').json()

        for field in ('agent_id', 'persona_name', 'role', 'status'):
            assert field in data, (
                f"field '{field}' must be present in /agent/info response"
            )
