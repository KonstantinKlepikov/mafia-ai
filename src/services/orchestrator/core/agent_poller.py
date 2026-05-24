import asyncio
from dataclasses import dataclass

import docker
import docker.errors
import httpx
from loguru import logger

from shared.models import AgentInfo, AgentStatus


@dataclass
class AgentEndpoint:
    """Connection details for a single agent container.

    Attrs:
        agent_id: Logical agent identifier, e.g. ``agent-1``.
        host: Docker service hostname reachable from the orchestrator container.
        port: HTTP port the agent's FastAPI server listens on.
        container_name: Docker container name used for lifecycle management.

    """

    agent_id: str
    host: str
    port: int
    container_name: str


class AgentPoller:
    """HTTP polling and Docker lifecycle manager for agent containers.

    Polls each agent's ``GET /agent/info`` endpoint and caches the result.
    Agents that fail to respond are marked ELIMINATED in the cache.
    Container stopping is executed via the Docker SDK in a thread executor to
    avoid blocking the asyncio event loop.

    Args:
        endpoints: Ordered list of all agent connection endpoints.
        docker_socket_url: Docker socket URL, e.g. ``unix:///var/run/docker.sock``.
        http_timeout: Per-request timeout in seconds for agent health checks.

    """

    def __init__(
        self,
        endpoints: list[AgentEndpoint],
        docker_socket_url: str,
        http_timeout: float = 5.0,
    ) -> None:
        self._endpoints: dict[str, AgentEndpoint] = {
            ep.agent_id: ep for ep in endpoints
        }
        self._cache: dict[str, AgentInfo] = {}
        self._http = httpx.AsyncClient(timeout=http_timeout)
        self._docker = docker.DockerClient(base_url=docker_socket_url)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def poll_agent(self, agent_id: str) -> AgentInfo | None:
        """Fetch ``/agent/info`` for one agent and update the local cache.

        On request failure the cached entry (if any) is updated to ELIMINATED
        so that callers detect unreachable containers as eliminated agents.

        Args:
            agent_id: ID of the agent to poll.

        Returns:
            Parsed AgentInfo on success, or None if the endpoint is unknown.

        """
        ep = self._endpoints.get(agent_id)
        if ep is None:
            return None

        url = f'http://{ep.host}:{ep.port}/agent/info'
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            info = AgentInfo.model_validate(resp.json())
            self._cache[agent_id] = info
            return info
        except Exception as exc:
            logger.warning(f'Poll failed for {agent_id}: {exc}')
            cached = self._cache.get(agent_id)
            if cached is not None:
                self._cache[agent_id] = cached.model_copy(
                    update={'status': AgentStatus.ELIMINATED}
                )
            return None

    async def poll_all(self, agent_ids: list[str]) -> dict[str, AgentInfo]:
        """Poll all given agents concurrently and return the updated cache.

        Args:
            agent_ids: IDs of agents to poll.

        Returns:
            Mapping of agent_id to AgentInfo for all agents present in cache
            after polling (successful or previously cached).

        """
        await asyncio.gather(
            *(self.poll_agent(aid) for aid in agent_ids),
            return_exceptions=True,
        )
        return {aid: self._cache[aid] for aid in agent_ids if aid in self._cache}

    def get_cached(self, agent_id: str) -> AgentInfo | None:
        """Return the last cached AgentInfo for an agent without polling.

        Args:
            agent_id: ID of the agent.

        Returns:
            Cached AgentInfo, or None if the agent has never been polled.

        """
        return self._cache.get(agent_id)

    def get_all_cached(self) -> dict[str, AgentInfo]:
        """Return a snapshot of all cached agent info entries."""
        return dict(self._cache)

    async def stop_container(self, agent_id: str) -> None:
        """Stop the Docker container of an agent (non-blocking).

        Runs the blocking Docker SDK call in a thread executor so it does not
        stall the event loop.

        Args:
            agent_id: ID of the agent whose container to stop.

        """
        ep = self._endpoints.get(agent_id)
        if ep is None:
            logger.warning(f'stop_container: unknown agent {agent_id}')
            return

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._stop_container_sync, ep.container_name
            )
            logger.info(f'Container stopped for agent {agent_id}: {ep.container_name}')
        except docker.errors.NotFound:
            logger.warning(f'Container {ep.container_name} not found; skipping stop')
        except Exception as exc:
            logger.error(f'Failed to stop container {ep.container_name}: {exc}')

    def _stop_container_sync(self, container_name: str) -> None:
        """Synchronous Docker stop call; intended for thread-executor use only."""
        container = self._docker.containers.get(container_name)
        container.stop(timeout=5)
