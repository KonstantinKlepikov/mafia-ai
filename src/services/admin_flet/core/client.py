"""Async HTTP client for Orchestrator REST API."""

import httpx
from loguru import logger

from shared.models import AgentInfo, GameState, HostDecision


class OrchestratorClientError(Exception):
    """Raised when orchestrator HTTP request fails."""


class AsyncOrchestratorClient:
    """Async wrapper over Orchestrator REST API.

    Args:
        base_url: Orchestrator base URL
        timeout: HTTP timeout in seconds

    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip('/')
        self._http = httpx.AsyncClient(base_url=self._base, timeout=timeout)

    async def close(self) -> None:
        """Close HTTP client connection."""
        await self._http.aclose()

    async def start_game(self) -> None:
        """POST /game/start — launch new game.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = await self._http.post('/game/start')
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OrchestratorClientError(f'start_game failed: {exc}') from exc

    async def get_state(self) -> GameState | None:
        """GET /game/state — return current game state or None on failure."""
        try:
            resp = await self._http.get('/game/state')
            resp.raise_for_status()
            return GameState.model_validate(resp.json())
        except Exception as exc:
            logger.debug(f'get_state failed: {exc}')
            return None

    async def post_decision(self, decision: HostDecision) -> None:
        """POST /game/host/decision — submit host action.

        Args:
            decision: APPROVE / REJECT / OVERRIDE with optional target_id.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = await self._http.post(
                '/game/host/decision',
                json=decision.model_dump(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OrchestratorClientError(f'post_decision failed: {exc}') from exc

    async def get_agents(self) -> dict[str, AgentInfo]:
        """GET /game/agents — return map of agent info or empty dict on failure."""
        try:
            resp = await self._http.get('/game/agents')
            resp.raise_for_status()
            return {
                agent_id: AgentInfo.model_validate(info)
                for agent_id, info in resp.json().items()
            }
        except Exception as exc:
            logger.debug(f'get_agents failed: {exc}')
            return {}

    async def ask_agent(self, agent_id: str, question: str) -> None:
        """POST /game/agents/{agent_id}/question — send question to agent.

        Args:
            agent_id: ID of agent to ask.
            question: Question text from host.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = await self._http.post(
                f'/game/agents/{agent_id}/question',
                json={'question': question},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OrchestratorClientError(f'ask_agent failed: {exc}') from exc
