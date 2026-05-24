"""Synchronous HTTP client for the Orchestrator REST API."""

import requests
from loguru import logger

from shared.models import AgentInfo, GameState, HostDecision


class OrchestratorClientError(Exception):
    """Raised when an orchestrator HTTP request fails."""


class OrchestratorClient:
    """Synchronous wrapper over the Orchestrator REST API.

    All methods return gracefully (None / empty dict) on network errors
    so the Streamlit panel remains functional while the orchestrator
    is temporarily unreachable.

    Args:
        base_url: Orchestrator base URL, e.g. ``http://mafia-ai-orchestrator:8081``.

    """

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip('/')

    def start_game(self) -> None:
        """POST /game/start — launch a new game.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = requests.post(f'{self._base}/game/start', timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OrchestratorClientError(str(exc)) from exc

    def get_state(self) -> GameState | None:
        """GET /game/state — return current game state, or None on failure."""
        try:
            resp = requests.get(f'{self._base}/game/state', timeout=5)
            resp.raise_for_status()
            return GameState.model_validate(resp.json())
        except Exception as exc:
            logger.warning(f'get_state failed: {exc}')
            return None

    def post_decision(self, decision: HostDecision) -> None:
        """POST /game/host/decision — submit a host action.

        Args:
            decision: APPROVE / REJECT / OVERRIDE with optional target_id.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = requests.post(
                f'{self._base}/game/host/decision',
                json=decision.model_dump(),
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OrchestratorClientError(str(exc)) from exc

    def get_agents(self) -> dict[str, AgentInfo]:
        """GET /game/agents — return map of alive agents, or {} on failure."""
        try:
            resp = requests.get(f'{self._base}/game/agents', timeout=5)
            resp.raise_for_status()
            return {
                agent_id: AgentInfo.model_validate(info)
                for agent_id, info in resp.json().items()
            }
        except Exception as exc:
            logger.warning(f'get_agents failed: {exc}')
            return {}

    def ask_agent(self, agent_id: str, question: str) -> str:
        """POST /game/agents/{agent_id}/question — send a question.

        Args:
            agent_id: ID of the agent to ask.
            question: Question text from the host.

        Returns:
            question_id UUID string for tracking the answer.

        Raises:
            OrchestratorClientError: On HTTP or network error.

        """
        try:
            resp = requests.post(
                f'{self._base}/game/agents/{agent_id}/question',
                json={'question_text': question},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()['question_id']
        except requests.RequestException as exc:
            raise OrchestratorClientError(str(exc)) from exc
