import random

import httpx
from loguru import logger

from shared.database import Database
from shared.models import (
    AgentRole,
    GamePhase,
    Message,
    SystemPrompt,
    TargetAudience,
)


class AgentLogic:
    """Logic for a single AI agent.

    Manages persona, message history, and LLM interactions.
    Does NOT handle RabbitMQ or HTTP endpoints - pure business logic.

    Args:
        agent_id: Unique agent identifier (e.g. 'agent-1').
        persona: SystemPrompt with character details.
        llm_client: HTTP client for LLM service.
        db: Database instance for state persistence.

    """

    def __init__(
        self,
        agent_id: str,
        persona: SystemPrompt,
        llm_client: httpx.AsyncClient,
        db: Database,
    ) -> None:
        self._agent_id = agent_id
        self._persona = persona
        self._llm_client = llm_client
        self._db = db

    async def generate_message(self, phase: GamePhase, game_round: int) -> str:
        """Generate a message for the current phase.

        Args:
            phase: Current game phase (NIGHT or DAY).
            game_round: Current round number.

        Returns:
            Generated message text.

        """
        state = await self._db.get_agent_state(self._agent_id)
        if state is None:
            raise ValueError(f'Agent {self._agent_id} not initialized')

        is_night = phase == GamePhase.NIGHT

        # Citizens don't speak during night
        if is_night and state.role != AgentRole.MAFIA:
            return ''

        if is_night:
            extra_prompt = (
                'It is nighttime. Discuss with your fellow mafia members '
                'who to eliminate. Speak as your character.'
            )
        else:
            extra_prompt = (
                'Share your thoughts on who might be the mafia. '
                'Speak as your character.'
            )

        text = await self._generate_llm_response(extra_prompt, max_tokens=150)

        # Store message in history
        target_audience = TargetAudience.MAFIA_ONLY if is_night else TargetAudience.ALL
        message = Message(
            sender_id=self._agent_id,
            content=text,
            phase=phase,
            round=game_round,
            target_audience=target_audience,
        )
        state.message_history.append(message)
        await self._db.upsert_agent_state(self._agent_id, state)

        logger.info(
            f'Agent {self._agent_id} generated message for phase {phase}: '
            f'{text[:50]}...'
        )
        return text

    async def generate_vote(
        self,
        candidates: list[str],
        is_night: bool,
        game_round: int,
    ) -> str:
        """Generate a vote for elimination.

        Args:
            candidates: List of alive agent IDs (excluding self).
            is_night: True for night vote, False for day vote.
            game_round: Current round number.

        Returns:
            Target agent ID to vote for.

        """
        if not candidates:
            return ''

        vote_action = (
            'eliminate at night' if is_night else 'vote to eliminate during the day'
        )
        extra_prompt = (
            f'It is time to vote. Living players: {", ".join(candidates)}. '
            f'Choose one player to {vote_action}. '
            'Respond with ONLY the player ID from the list above, nothing else.'
        )

        try:
            raw = await self._generate_llm_response(extra_prompt, max_tokens=50)
        except Exception as exc:
            logger.error(f'Agent {self._agent_id} LLM call failed for vote: {exc}')
            raw = ''

        target_id = raw.strip()
        if target_id not in candidates:
            target_id = random.choice(candidates)
            logger.warning(
                f'Agent {self._agent_id} LLM vote response invalid, using '
                f'random: {target_id}'
            )

        logger.info(
            f'Agent {self._agent_id} voted for {target_id} '
            f'({"night" if is_night else "day"})'
        )
        return target_id

    async def answer_question(self, question_text: str) -> str:
        """Generate answer to host question.

        Args:
            question_text: Question from the host.

        Returns:
            Generated answer text.

        """
        extra_prompt = (
            f'The host asks you: "{question_text}". Answer in character, concisely.'
        )

        try:
            text = await self._generate_llm_response(extra_prompt, max_tokens=150)
        except Exception as exc:
            logger.error(f'Agent {self._agent_id} LLM call failed for question: {exc}')
            text = 'I cannot answer right now.'

        logger.info(f'Agent {self._agent_id} answered question: {text[:50]}...')
        return text

    async def add_message_to_history(self, message: Message) -> None:
        """Add external message to agent's history.

        Args:
            message: Message from another agent or system.

        """
        # Skip own messages
        if message.sender_id == self._agent_id:
            return

        state = await self._db.get_agent_state(self._agent_id)
        if state is None:
            return

        state.message_history.append(message)
        await self._db.upsert_agent_state(self._agent_id, state)

        logger.debug(
            f'Agent {self._agent_id} added message from {message.sender_id} to history'
        )

    async def _generate_llm_response(self, extra_user_msg: str, max_tokens: int) -> str:
        """Build context from history and call the LLM MCP API.

        Args:
            extra_user_msg: Instruction appended as the final user turn.
            max_tokens: Upper bound on generated tokens.

        Returns:
            Generated text from the LLM.

        Raises:
            httpx.HTTPStatusError: On non-2xx response from the LLM service.

        """
        state = await self._db.get_agent_state(self._agent_id)
        if state is None:
            raise ValueError(f'Agent {self._agent_id} not initialized')

        history: list[dict[str, str]] = []
        for msg in state.message_history:
            if msg.sender_id == self._agent_id:
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

        response = await self._llm_client.post('/mcp/generate', json=payload)
        response.raise_for_status()
        return response.json()['text']
