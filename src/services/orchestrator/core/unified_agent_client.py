"""HTTP client for Unified Agent Service.

Replaces AgentPoller and Docker SDK with REST API calls to the unified
agent service.
"""

from typing import Any

import httpx
from loguru import logger

from shared.models import AgentRole, AgentState


class UnifiedAgentClient:
    """HTTP client for unified agent service.

    Manages agent lifecycle through REST API instead of Docker containers
    and RabbitMQ messaging.

    Args:
        base_url: Base URL of unified agent service.
        http_timeout: Request timeout in seconds.

    """

    def __init__(
        self,
        base_url: str,
        http_timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._http = httpx.AsyncClient(timeout=http_timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def initialize_agent(
        self, agent_id: str, role: AgentRole, persona_id: str
    ) -> None:
        """Initialize a new agent instance.

        Args:
            agent_id: Unique agent identifier.
            role: Agent role (MAFIA or CITIZEN).
            persona_id: Persona ID from config/prompts.yaml.

        Raises:
            httpx.HTTPStatusError: If initialization fails.

        """
        url = f'{self._base_url}/agents/{agent_id}/init'
        payload = {
            'role': role.value,
            'persona_id': persona_id,
        }

        response = await self._http.post(url, json=payload)
        response.raise_for_status()

        logger.info(f'Initialized agent {agent_id} with role {role}')

    async def act(
        self, agent_id: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an action for a specific agent.

        Args:
            agent_id: Agent to act.
            action: Action type ('generate_message', 'vote',
                'answer_question', 'add_message').
            params: Action-specific parameters.

        Returns:
            Action result dictionary.

        Raises:
            httpx.HTTPStatusError: If action fails.

        """
        url = f'{self._base_url}/agents/{agent_id}/act'
        payload = {
            'action': action,
            'params': params,
        }

        response = await self._http.post(url, json=payload)
        response.raise_for_status()

        return response.json()

    async def get_state(self, agent_id: str) -> AgentState | None:
        """Get current agent state.

        Args:
            agent_id: Agent to query.

        Returns:
            AgentState on success, None if agent not found or unreachable.

        """
        url = f'{self._base_url}/agents/{agent_id}/state'

        try:
            response = await self._http.get(url)
            response.raise_for_status()
            data = response.json()
            return AgentState(**data)
        except httpx.HTTPError as exc:
            logger.warning(f'Failed to get state for {agent_id}: {exc}')
            return None

    async def eliminate_agent(self, agent_id: str) -> None:
        """Eliminate an agent (mark as eliminated and remove from manager).

        Args:
            agent_id: Agent to eliminate.

        Raises:
            httpx.HTTPStatusError: If elimination fails.

        """
        url = f'{self._base_url}/agents/{agent_id}'

        response = await self._http.delete(url)
        response.raise_for_status()

        logger.info(f'Eliminated agent {agent_id}')

    async def generate_message(
        self, agent_id: str, phase: str, game_round: int
    ) -> str:
        """Request agent to generate a message for current phase.

        Args:
            agent_id: Agent to act.
            phase: Game phase ('NIGHT' or 'DAY').
            game_round: Current game round number.

        Returns:
            Generated message text.

        Raises:
            httpx.HTTPStatusError: If generation fails.

        """
        result = await self.act(
            agent_id,
            'generate_message',
            {'phase': phase, 'game_round': game_round},
        )
        return result.get('message', '')

    async def vote(
        self, agent_id: str, candidates: list[str], is_night: bool, game_round: int
    ) -> str:
        """Request agent to vote for elimination.

        Args:
            agent_id: Agent to act.
            candidates: List of agent IDs to choose from.
            is_night: True for night vote (mafia), False for day vote.
            game_round: Current game round number.

        Returns:
            Voted agent ID.

        Raises:
            httpx.HTTPStatusError: If vote fails.

        """
        result = await self.act(
            agent_id,
            'vote',
            {
                'candidates': candidates,
                'is_night': is_night,
                'game_round': game_round,
            },
        )
        return result.get('voted_for', '')

    async def answer_question(self, agent_id: str, question_text: str) -> str:
        """Request agent to answer a host question.

        Args:
            agent_id: Agent to query.
            question_text: Question from host.

        Returns:
            Agent's answer text.

        Raises:
            httpx.HTTPStatusError: If answer fails.

        """
        result = await self.act(
            agent_id, 'answer_question', {'question_text': question_text}
        )
        return result.get('answer', '')

    async def add_message_to_history(
        self, agent_id: str, role: str, content: str
    ) -> None:
        """Add a message to agent's conversation history.

        Args:
            agent_id: Agent to update.
            role: Message role ('user' or 'assistant').
            content: Message content.

        Raises:
            httpx.HTTPStatusError: If update fails.

        """
        await self.act(
            agent_id, 'add_message', {'role': role, 'content': content}
        )
