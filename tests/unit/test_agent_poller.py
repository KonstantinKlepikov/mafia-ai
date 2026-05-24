"""Unit tests for orchestrator AgentPoller."""

from unittest.mock import AsyncMock, MagicMock

import docker
import docker.errors
import httpx
import pytest
from _pytest.monkeypatch import MonkeyPatch

from services.orchestrator.core.agent_poller import AgentEndpoint, AgentPoller
from shared.models import AgentInfo, AgentRole, AgentStatus


def _make_endpoint(n: int = 1) -> AgentEndpoint:
    return AgentEndpoint(
        agent_id=f'agent-{n}',
        host=f'mafia-ai-agent-{n}',
        port=8100,
        container_name=f'mafia-ai-agent-{n}',
    )


def _make_info(
    agent_id: str = 'agent-1',
    status: AgentStatus = AgentStatus.ALIVE,
) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        persona_name='persona_test',
        role=AgentRole.CITIZEN,
        status=status,
    )


def _make_http_response(agent_id: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = _make_info(agent_id).model_dump()
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def mock_docker(monkeypatch: MonkeyPatch) -> MagicMock:
    """Patch docker.DockerClient to avoid real socket connections."""
    client = MagicMock()
    monkeypatch.setattr(docker, 'DockerClient', lambda base_url: client)
    return client


@pytest.fixture
def poller(mock_docker: MagicMock) -> AgentPoller:
    """AgentPoller with 3 agents (agent-1..3) and mocked HTTP + Docker."""
    endpoints = [_make_endpoint(n) for n in range(1, 4)]
    p = AgentPoller(
        endpoints=endpoints,
        docker_socket_url='unix:///var/run/docker.sock',
    )
    p._http = AsyncMock()
    return p


class TestAgentPollerInit:
    """Tests for AgentPoller construction."""

    def test_endpoints_indexed_by_agent_id(self, mock_docker: MagicMock) -> None:
        """Test _endpoints is a dict keyed by agent_id."""
        ep = _make_endpoint(1)
        p = AgentPoller(endpoints=[ep], docker_socket_url='unix:///var/run/docker.sock')

        assert 'agent-1' in p._endpoints, 'agent-1 must be a key in _endpoints'

    def test_all_endpoints_stored(self, mock_docker: MagicMock) -> None:
        """Test all provided endpoints are stored."""
        endpoints = [_make_endpoint(n) for n in range(1, 4)]
        p = AgentPoller(
            endpoints=endpoints, docker_socket_url='unix:///var/run/docker.sock'
        )

        assert set(p._endpoints.keys()) == {'agent-1', 'agent-2', 'agent-3'}, (
            f'wrong keys: {set(p._endpoints.keys())}'
        )

    def test_cache_is_empty_on_init(self, mock_docker: MagicMock) -> None:
        """Test the poll cache starts empty."""
        p = AgentPoller(
            endpoints=[_make_endpoint()],
            docker_socket_url='unix:///var/run/docker.sock',
        )

        assert p._cache == {}, f'cache must be empty on init, got {p._cache}'


class TestAgentPollerClose:
    """Tests for AgentPoller.close."""

    async def test_close_calls_http_aclose(self, poller: AgentPoller) -> None:
        """Test close delegates to aclose on the underlying HTTP client."""
        await poller.close()

        poller._http.aclose.assert_called_once()  # type: ignore[attr-defined]


class TestAgentPollerPollAgent:
    """Tests for AgentPoller.poll_agent."""

    async def test_success_returns_agent_info(self, poller: AgentPoller) -> None:
        """Test poll_agent returns parsed AgentInfo on a 200 response."""
        expected = _make_info('agent-1')
        poller._http.get.return_value = (  # type: ignore[attr-defined]
            _make_http_response('agent-1')
        )

        result = await poller.poll_agent('agent-1')

        assert result == expected, f'expected {expected}, got {result}'

    async def test_success_updates_cache(self, poller: AgentPoller) -> None:
        """Test poll_agent stores the parsed result in _cache."""
        expected = _make_info('agent-2')
        poller._http.get.return_value = (  # type: ignore[attr-defined]
            _make_http_response('agent-2')
        )

        await poller.poll_agent('agent-2')

        assert poller._cache.get('agent-2') == expected, (
            'agent-2 must be cached after a successful poll'
        )

    async def test_unknown_agent_id_returns_none(self, poller: AgentPoller) -> None:
        """Test poll_agent returns None without making a request for unknown id."""
        result = await poller.poll_agent('agent-99')

        assert result is None, f'expected None for unknown agent, got {result}'
        poller._http.get.assert_not_called()  # type: ignore[attr-defined]

    async def test_http_error_returns_none(self, poller: AgentPoller) -> None:
        """Test poll_agent returns None when the HTTP request raises."""
        poller._http.get.side_effect = (  # type: ignore[attr-defined]
            httpx.ConnectError('connection refused')
        )

        result = await poller.poll_agent('agent-1')

        assert result is None, f'expected None on HTTP error, got {result}'

    async def test_http_error_marks_cached_entry_eliminated(
        self, poller: AgentPoller
    ) -> None:
        """Test poll_agent sets cached status to ELIMINATED on failure."""
        poller._cache['agent-1'] = _make_info('agent-1', AgentStatus.ALIVE)
        poller._http.get.side_effect = (  # type: ignore[attr-defined]
            httpx.ConnectError('connection refused')
        )

        await poller.poll_agent('agent-1')

        cached = poller._cache.get('agent-1')
        assert cached is not None, 'cache entry must still exist after failure'
        assert cached.status == AgentStatus.ELIMINATED, (
            f'status must be ELIMINATED after failure, got {cached.status}'
        )

    async def test_http_error_with_no_prior_cache_stays_absent(
        self, poller: AgentPoller
    ) -> None:
        """Test poll_agent does not add an entry to cache on first-time failure."""
        poller._http.get.side_effect = (  # type: ignore[attr-defined]
            httpx.ConnectError('connection refused')
        )

        await poller.poll_agent('agent-1')

        assert 'agent-1' not in poller._cache, (
            'agent-1 must not appear in cache without a prior successful poll'
        )

    async def test_uses_correct_url(self, poller: AgentPoller) -> None:
        """Test poll_agent builds the URL from endpoint host and port."""
        poller._http.get.return_value = (  # type: ignore[attr-defined]
            _make_http_response('agent-1')
        )

        await poller.poll_agent('agent-1')

        poller._http.get.assert_called_once_with(  # type: ignore[attr-defined]
            'http://mafia-ai-agent-1:8100/agent/info'
        )


class TestAgentPollerPollAll:
    """Tests for AgentPoller.poll_all."""

    async def test_returns_all_successfully_polled_entries(
        self, poller: AgentPoller, monkeypatch: MonkeyPatch
    ) -> None:
        """Test poll_all returns cache entries for all agents that responded."""

        async def mock_poll_agent(agent_id: str) -> AgentInfo:
            info = _make_info(agent_id)
            poller._cache[agent_id] = info
            return info

        monkeypatch.setattr(poller, 'poll_agent', mock_poll_agent)

        result = await poller.poll_all(['agent-1', 'agent-2', 'agent-3'])

        assert set(result.keys()) == {'agent-1', 'agent-2', 'agent-3'}, (
            f'all 3 agents must be returned, got {set(result.keys())}'
        )

    async def test_excludes_agents_absent_from_cache(
        self, poller: AgentPoller, monkeypatch: MonkeyPatch
    ) -> None:
        """Test poll_all omits agents whose poll failed and had no prior cache."""

        async def mock_poll_agent(agent_id: str) -> AgentInfo | None:
            if agent_id == 'agent-1':
                info = _make_info('agent-1')
                poller._cache['agent-1'] = info
                return info
            return None

        monkeypatch.setattr(poller, 'poll_agent', mock_poll_agent)

        result = await poller.poll_all(['agent-1', 'agent-2', 'agent-3'])

        assert 'agent-1' in result, 'agent-1 must be in result (successful poll)'
        assert 'agent-2' not in result, 'agent-2 must be absent (no cache)'
        assert 'agent-3' not in result, 'agent-3 must be absent (no cache)'

    async def test_polls_all_provided_agent_ids(
        self, poller: AgentPoller, monkeypatch: MonkeyPatch
    ) -> None:
        """Test poll_all calls poll_agent for every id in the input list."""
        polled: list[str] = []

        async def mock_poll_agent(agent_id: str) -> None:
            polled.append(agent_id)

        monkeypatch.setattr(poller, 'poll_agent', mock_poll_agent)

        await poller.poll_all(['agent-1', 'agent-3'])

        assert set(polled) == {'agent-1', 'agent-3'}, (
            f'poll_agent must be called for each id, got {polled}'
        )


class TestAgentPollerGetCached:
    """Tests for AgentPoller.get_cached."""

    def test_returns_none_before_any_poll(self, poller: AgentPoller) -> None:
        """Test get_cached returns None when the agent was never polled."""
        result = poller.get_cached('agent-1')

        assert result is None, f'expected None before first poll, got {result}'

    def test_returns_info_when_cache_is_populated(self, poller: AgentPoller) -> None:
        """Test get_cached returns the previously stored AgentInfo."""
        info = _make_info('agent-2')
        poller._cache['agent-2'] = info

        result = poller.get_cached('agent-2')

        assert result == info, f'expected {info}, got {result}'

    def test_unknown_agent_returns_none(self, poller: AgentPoller) -> None:
        """Test get_cached returns None for an agent not in cache."""
        poller._cache['agent-1'] = _make_info('agent-1')

        result = poller.get_cached('agent-99')

        assert result is None, f'expected None for unknown agent, got {result}'


class TestAgentPollerGetAllCached:
    """Tests for AgentPoller.get_all_cached."""

    def test_returns_empty_dict_on_fresh_poller(self, poller: AgentPoller) -> None:
        """Test get_all_cached returns an empty dict before any poll."""
        result = poller.get_all_cached()

        assert result == {}, f'expected empty dict, got {result}'

    def test_returns_all_populated_entries(self, poller: AgentPoller) -> None:
        """Test get_all_cached includes every entry present in the cache."""
        poller._cache['agent-1'] = _make_info('agent-1')
        poller._cache['agent-3'] = _make_info('agent-3')

        result = poller.get_all_cached()

        assert set(result.keys()) == {'agent-1', 'agent-3'}, (
            f'expected agent-1 and agent-3, got {set(result.keys())}'
        )

    def test_returns_a_copy_not_the_cache_itself(self, poller: AgentPoller) -> None:
        """Test mutating the returned dict does not affect the internal cache."""
        poller._cache['agent-1'] = _make_info('agent-1')

        result = poller.get_all_cached()
        result['agent-2'] = _make_info('agent-2')

        assert 'agent-2' not in poller._cache, (
            'mutating returned dict must not affect internal cache'
        )


class TestAgentPollerStopContainer:
    """Tests for AgentPoller.stop_container."""

    async def test_unknown_agent_does_not_raise(self, poller: AgentPoller) -> None:
        """Test stop_container silently ignores an unknown agent_id."""
        await poller.stop_container('agent-99')  # must not raise

    async def test_calls_docker_containers_get_and_stop(
        self, poller: AgentPoller, mock_docker: MagicMock
    ) -> None:
        """Test stop_container calls containers.get then stop(timeout=5)."""
        mock_container = MagicMock()
        mock_docker.containers.get.return_value = mock_container

        await poller.stop_container('agent-1')

        mock_docker.containers.get.assert_called_once_with('mafia-ai-agent-1')
        mock_container.stop.assert_called_once_with(timeout=5)

    async def test_not_found_error_does_not_raise(
        self, poller: AgentPoller, mock_docker: MagicMock
    ) -> None:
        """Test stop_container does not raise when the container is already gone."""
        mock_docker.containers.get.side_effect = docker.errors.NotFound('gone')

        await poller.stop_container('agent-1')  # must not raise

    async def test_generic_docker_error_does_not_raise(
        self, poller: AgentPoller, mock_docker: MagicMock
    ) -> None:
        """Test stop_container does not propagate unexpected Docker errors."""
        mock_docker.containers.get.side_effect = RuntimeError('daemon error')

        await poller.stop_container('agent-1')  # must not raise

    async def test_uses_container_name_from_endpoint(
        self, poller: AgentPoller, mock_docker: MagicMock
    ) -> None:
        """Test stop_container uses the container_name from the endpoint,
        not agent_id.
        """
        mock_container = MagicMock()
        mock_docker.containers.get.return_value = mock_container

        await poller.stop_container('agent-3')

        mock_docker.containers.get.assert_called_once_with('mafia-ai-agent-3')
