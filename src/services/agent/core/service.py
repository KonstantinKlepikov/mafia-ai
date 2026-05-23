"""Agent service: full game-cycle logic for a single agent.

The service connects to RabbitMQ on startup, loads its persona from VectorDB,
subscribes to all relevant routing keys and reacts to:

- ``game.init.{agent_id}``    — role assignment from the orchestrator
- ``game.state``              — phase changes and eliminations
- ``message.all``             — public game messages (stored in history)
- ``message.mafia``           — mafia-only messages (subscribed only after
                                receiving a MAFIA role)
- ``game.turn.{agent_id}``    — signal to generate and publish a message
- ``host.question.{agent_id}``— host question that requires an answer
"""

import json
import random

import httpx
from loguru import logger

from shared.messaging import MessagingClient
from shared.models import (
    AgentAnswer,
    AgentInfo,
    AgentInit,
    AgentRole,
    AgentState,
    AgentStatus,
    GamePhase,
    GameState,
    HostQuestion,
    Message,
    SystemPrompt,
    TargetAudience,
    VoteEvent,
)
from shared.vectordb_client import VectorDBClient

from ..config import AgentSettings


class AgentService:
    """Full-cycle agent: subscribes to RabbitMQ, calls LLM, publishes responses.

    Args:
        settings: Populated :class:`~agent.config.AgentSettings` instance.

    """

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self.__persona: SystemPrompt | None = None
        self._state: AgentState | None = None
        self._status: AgentStatus = AgentStatus.ALIVE
        self._current_game_state: GameState | None = None
        self._messaging: MessagingClient = MessagingClient(settings.amqp_url)
        self._http_client = httpx.AsyncClient(
            base_url=self._settings.llm_url,
            timeout=120.0,
        )

    @property
    def _persona(self) -> SystemPrompt:
        """Persona data"""
        if self.__persona is None:
            self.__persona = self._load_persona()
            logger.info(
                f'Agent {self._settings.agent_id} loaded persona: {self.__persona.name}'
            )
        return self.__persona

    async def start(self) -> None:
        """Load persona, open connections and subscribe to all routing keys."""

        await self._messaging.connect()

        agent_id = self._settings.agent_id
        await self._messaging.subscribe(f'game.init.{agent_id}', self._on_game_init)
        await self._messaging.subscribe('game.state', self._on_game_state)
        await self._messaging.subscribe('message.all', self._on_message)
        await self._messaging.subscribe(f'game.turn.{agent_id}', self._on_turn)
        await self._messaging.subscribe(
            f'host.question.{agent_id}', self._on_host_question
        )

        logger.info(f'Agent {agent_id} started and subscribed to RabbitMQ')

    async def stop(self) -> None:
        """Close RabbitMQ connection and HTTP client."""
        await self._messaging.close()
        if self._http_client is not None:
            await self._http_client.aclose()
        logger.info(f'Agent {self._settings.agent_id} stopped')

    def get_info(self) -> AgentInfo:
        """Return current agent info for the REST API.

        Before role assignment is received the role defaults to CITIZEN.
        """
        role = self._state.role if self._state else AgentRole.CITIZEN
        return AgentInfo(
            agent_id=self._settings.agent_id,
            persona_name=self._persona.name,
            role=role,
            status=self._status,
        )

    # ------------------------------------------------------------------
    # RabbitMQ callbacks
    # ------------------------------------------------------------------

    async def _on_game_init(self, routing_key: str, body: bytes) -> None:
        """Handle role assignment message from the orchestrator."""
        try:
            init = AgentInit.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} failed to parse game.init: {exc}'
            )
            return

        self._state = AgentState(
            agent_id=self._settings.agent_id,
            role=init.role,
            persona_id=self._settings.persona_id,
        )
        self._status = AgentStatus.ALIVE

        logger.info(f'Agent {self._settings.agent_id} received role: {init.role}')

        # Subscribe to mafia channel only after confirming the role
        if init.role == AgentRole.MAFIA:
            await self._messaging.subscribe('message.mafia', self._on_message)

    async def _on_game_state(self, routing_key: str, body: bytes) -> None:
        """Handle game state updates: phase changes and eliminations."""
        try:
            game_state = GameState.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} failed to parse game.state: {exc}'
            )
            return

        self._current_game_state = game_state

        # Mark this agent as eliminated if it appears in the eliminated list
        if (
            self._settings.agent_id in game_state.eliminated
            and self._status == AgentStatus.ALIVE
        ):
            self._status = AgentStatus.ELIMINATED
            logger.info(f'Agent {self._settings.agent_id} is eliminated')
            return

        if self._status != AgentStatus.ALIVE or self._state is None:
            return

        # Trigger vote generation on entering voting phases
        if (
            game_state.phase == GamePhase.NIGHT_VOTE
            and self._state.role == AgentRole.MAFIA
        ):
            await self._generate_and_publish_vote(game_state, is_night=True)
        elif game_state.phase == GamePhase.DAY_VOTE:
            await self._generate_and_publish_vote(game_state, is_night=False)

    async def _on_message(self, routing_key: str, body: bytes) -> None:
        """Store incoming messages in the local history."""
        try:
            message = Message.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} failed to parse message: {exc}'
            )
            return

        # Skip own messages — they are added directly after publishing
        if message.sender_id == self._settings.agent_id:
            return

        if self._state is not None:
            self._state.message_history.append(message)

        logger.debug(
            f'Agent {self._settings.agent_id} stored message from {message.sender_id}'
        )

    async def _on_turn(self, routing_key: str, body: bytes) -> None:
        """Generate a message on the agent's turn and publish it."""
        if self._status != AgentStatus.ALIVE or self._state is None:
            return

        phase = (
            self._current_game_state.phase
            if self._current_game_state
            else GamePhase.DAY
        )

        # Citizens do not speak during night phase
        if phase == GamePhase.NIGHT and self._state.role != AgentRole.MAFIA:
            return

        is_night = phase == GamePhase.NIGHT
        if is_night:
            extra_prompt = (
                'It is nighttime. Discuss with your fellow mafia members '
                'who to eliminate. Speak as your character.'
            )
            target_audience = TargetAudience.MAFIA_ONLY
            publish_key = 'message.mafia'
        else:
            extra_prompt = (
                'Share your thoughts on who might be the mafia. '
                'Speak as your character.'
            )
            target_audience = TargetAudience.ALL
            publish_key = 'message.all'

        try:
            text = await self._generate_llm_response(
                extra_prompt,
                self._settings.message_max_tokens,
            )
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} LLM call failed on turn: {exc}'
            )
            return

        game_round = self._current_game_state.round if self._current_game_state else 0
        message = Message(
            sender_id=self._settings.agent_id,
            content=text,
            phase=phase,
            round=game_round,
            target_audience=target_audience,
        )

        await self._messaging.publish(publish_key, message)
        self._state.message_history.append(message)

        logger.info(
            f'Agent {self._settings.agent_id} published message during phase {phase}'
        )

    async def _on_host_question(self, routing_key: str, body: bytes) -> None:
        """Generate and publish an answer to a host question."""
        try:
            question = HostQuestion.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} failed to parse host question: {exc}'
            )
            return

        extra_prompt = (
            f'The host asks you: "{question.question_text}". '
            'Answer in character, concisely.'
        )

        try:
            text = await self._generate_llm_response(
                extra_prompt,
                self._settings.message_max_tokens,
            )
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} LLM call failed on host '
                f'question {question.question_id}: {exc}'
            )
            return

        answer = AgentAnswer(
            question_id=question.question_id,
            agent_id=self._settings.agent_id,
            answer_text=text,
        )
        await self._messaging.publish(f'host.answer.{question.question_id}', answer)

        logger.info(
            f'Agent {self._settings.agent_id} answered question {question.question_id}'
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_and_publish_vote(
        self,
        game_state: GameState,
        is_night: bool,
    ) -> None:
        """Generate a vote via LLM and publish a VoteEvent."""
        if self._state is None:
            return

        candidates = [
            a for a in game_state.alive_agents if a != self._settings.agent_id
        ]
        if not candidates:
            return

        vote_action = (
            'eliminate at night' if is_night else 'vote to eliminate during the day'
        )
        extra_prompt = (
            f'It is time to vote. Living players: {", ".join(candidates)}. '
            f'Choose one player to {vote_action}. '
            'Respond with ONLY the player ID from the list above, nothing else.'
        )

        try:
            raw = await self._generate_llm_response(
                extra_prompt,
                self._settings.vote_max_tokens,
            )
        except Exception as exc:
            logger.error(
                f'Agent {self._settings.agent_id} LLM call failed for vote: {exc}'
            )
            raw = ''

        target_id = raw.strip()
        if target_id not in candidates:
            target_id = random.choice(candidates)
            logger.warning(
                f'Agent {self._settings.agent_id} LLM vote response invalid, using '
                f'random: {target_id}'
            )

        phase = GamePhase.NIGHT_VOTE if is_night else GamePhase.DAY_VOTE
        publish_key = 'vote.night' if is_night else 'vote.day'

        vote = VoteEvent(
            voter_id=self._settings.agent_id,
            target_id=target_id,
            phase=phase,
            round=game_state.round,
        )
        await self._messaging.publish(publish_key, vote)

        logger.info(
            f'Agent {self._settings.agent_id} voted for {target_id} '
            f'({"night" if is_night else "day"})'
        )

    async def _generate_llm_response(self, extra_user_msg: str, max_tokens: int) -> str:
        """Build context from history and call the LLM MCP API.

        Args:
            extra_user_msg: Instruction appended as the final user turn.
            max_tokens: Upper bound on generated tokens.

        Returns:
            Generated text from the LLM.

        Raises:
            RuntimeError: If the service has not been started.
            httpx.HTTPStatusError: On non-2xx response from the LLM service.

        """
        history: list[dict[str, str]] = []
        if self._state:
            for msg in self._state.message_history:
                if msg.sender_id == self._settings.agent_id:
                    history.append({'role': 'assistant', 'content': msg.content})
                else:
                    history.append(
                        {
                            'role': 'user',
                            'content': f'[{msg.sender_id}]: {msg.content}',
                        }
                    )

        history.append({'role': 'user', 'content': extra_user_msg})

        payload = {
            'system_prompt': self._persona.prompt,
            'messages': history,
            'max_tokens': max_tokens,
        }

        response = await self._http_client.post('/mcp/generate', json=payload)
        response.raise_for_status()
        return response.json()['text']

    def _load_persona(self) -> SystemPrompt:
        """Load persona from VectorDB using PERSONA_ID (UUID or name).

        Tries UUID lookup first; falls back to name lookup.

        Raises:
            ValueError: If no matching persona is found.

        """
        client = VectorDBClient(
            host=self._settings.vectordb_host,
            port=self._settings.vectordb_port,
        )
        persona_id = self._settings.persona_id

        try:
            return client.get_persona(persona_id)
        except ValueError:
            pass

        # Fallback: treat persona_id as a name
        return client.get_persona_by_name(persona_id)
