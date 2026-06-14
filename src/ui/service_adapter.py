"""Adapter for direct GameService access from UI components.

This module replaces AsyncOrchestratorClient by providing direct method
invocation instead of HTTP API calls.
"""

from loguru import logger

from shared.models import AgentInfo, GameState, HostDecision

from ..core.service import GameService


class GameServiceAdapterError(Exception):
    """Raised when game service operation fails."""


class GameServiceAdapter:
    """Adapter providing UI-friendly interface to GameService.

    Replaces HTTP-based AsyncOrchestratorClient with direct method calls.
    Provides the same interface to minimize UI code changes.

    Args:
        game_service: GameService instance to wrap.

    """

    def __init__(self, game_service: GameService) -> None:
        self._service = game_service

    async def close(self) -> None:
        """Close adapter (no-op for compatibility)."""
        pass

    async def start_game(self) -> None:
        """Start a new game.

        Raises:
            GameServiceAdapterError: On game initialization error.

        """
        try:
            await self._service.begin_game()
        except RuntimeError as exc:
            raise GameServiceAdapterError(f'start_game failed: {exc}') from exc
        except Exception as exc:
            logger.error(f'Unexpected error in start_game: {exc}')
            raise GameServiceAdapterError(f'start_game failed: {exc}') from exc

    async def get_state(self) -> GameState | None:
        """Get current game state.

        Returns:
            Current GameState or None on failure.

        """
        try:
            return self._service.get_game_state()
        except Exception as exc:
            logger.debug(f'get_state failed: {exc}')
            return None

    async def post_decision(self, decision: HostDecision) -> None:
        """Submit host decision.

        Args:
            decision: APPROVE / REJECT / OVERRIDE with optional target_id.

        Raises:
            GameServiceAdapterError: On submission error.

        """
        try:
            self._service.submit_host_decision(decision)
        except Exception as exc:
            logger.error(f'post_decision failed: {exc}')
            raise GameServiceAdapterError(f'post_decision failed: {exc}') from exc

    async def get_agents(self) -> dict[str, AgentInfo]:
        """Get info for all agents.

        Returns:
            Map of agent_id to AgentInfo or empty dict on failure.

        """
        try:
            return await self._service.get_agents_info()
        except Exception as exc:
            logger.debug(f'get_agents failed: {exc}')
            return {}

    async def ask_agent(self, agent_id: str, question: str) -> None:
        """Send question to agent.

        Args:
            agent_id: ID of agent to ask.
            question: Question text from host.

        Raises:
            GameServiceAdapterError: On communication error.

        """
        try:
            answer = await self._service.ask_agent(agent_id, question)
            if answer is None:
                raise GameServiceAdapterError(f'Agent {agent_id} did not respond')
            logger.info(f'Agent {agent_id} answered: {answer[:100]}...')
        except Exception as exc:
            logger.error(f'ask_agent failed: {exc}')
            raise GameServiceAdapterError(f'ask_agent failed: {exc}') from exc
