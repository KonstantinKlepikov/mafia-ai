from loguru import logger
from ollama import AsyncClient

from config import MafiaSettings
from core.crud import Database
from schemas import (
    GamePhase,
    LLMRequest,
    Message,
    Persona,
    SystemPromptKey,
    TargetAudience,
    VotingError,
    GameState,
)


class AgentLogic:
    """Logic for a single AI agent.

    Manages persona, message history, and LLM interactions.
    Does NOT handle RabbitMQ or HTTP endpoints - pure business logic.

    Args:
        agent_id (int): agent identifier.
        persona (Persona): character details.
        db (Database): instance for state persistence.
        ollama (AsyncClient): ollama client

    """

    def __init__(
        self,
        agent_id: int,
        persona: Persona,
        db: Database,
        ollama: AsyncClient,
        settings: MafiaSettings,
    ) -> None:
        self.agent_id = agent_id
        self.persona = persona
        self.db = db
        self.settings = settings
        self.ollama = ollama

    async def generate_message(self, game_state: GameState) -> str:
        """Generate a message for the current phase.

        Args:
            game_state (GameState): Current game state.

        Returns:
            Generated message text.

        TODO: test me

        """
        hidden = True if game_state.phase == GamePhase.NIGHT else False

        phase_prompt = (
            await self.db.get_system_prompt(key=SystemPromptKey.night_speak)
            if hidden
            else await self.db.get_system_prompt(key=SystemPromptKey.day_speak)
        )

        summary = await self.db.get_agent_summary(agent_id=self.agent_id)
        messages = await self.db.get_last_conversation(
            limit=10
        )  # TODO: move limit to config

        request = LLMRequest(
            persona_prompt=self.persona.prompt,
            phase_prompt=phase_prompt,
            summary=summary,
            messages=messages,
            max_tokens=self.settings.message_max_tokens,
        )

        text = await self._agent_message(request=request)

        message = Message(
            agent_id=self.agent_id,
            content=text,
            phase=game_state.phase,
            round=game_state.round,
            target=TargetAudience.MAFIA_ONLY if hidden else TargetAudience.ALL,
        )
        await self.db.insert_message(message=message)
        logger.info(f'Agent {self.agent_id} generated message for: {game_state.phase}')
        logger.debug(f'Message text: {text}')
        return text

    async def generate_vote(self, game_state: GameState) -> int:
        """Generate a vote for elimination.

        Args:
            game_state (GameState): Current game state.

        Raises:
            ValueError: epty list of candidates
            VotingError: wrong llm voting

        Returns:
            Target agent ID to vote for.

        TODO: test me

        """
        hidden = True if game_state.phase == GamePhase.NIGHT else False
        candidates = await self.db.get_agents_ids()
        if hidden:
            mafia = await self.db.get_mafia_ids()
            candidates = [i for i in candidates if i not in mafia]

        if not candidates:
            raise ValueError('Empty list of candidates')

        vote_template = await self.db.get_system_prompt(
            key=SystemPromptKey.vote_template
        )

        phase_prompt = vote_template.format(
            vote_action='eliminate at night'
            if hidden
            else 'vote to eliminate during the day',
            candidates=', '.join(map(str, candidates)),
        )

        summary = self.db.get_agent_summary(agent_id=self.agent_id)
        messages = self.db.get_last_conversation(limit=10)  # TODO: move limit to config

        request = LLMRequest(
            persona_prompt=self.persona.prompt,
            phase_prompt=phase_prompt,
            summary=summary,
            messages=messages,
            max_tokens=1,
        )

        target_id = await self._agent_message(request=request)

        try:
            target_id = int(target_id.strip())
            if target_id not in candidates:
                raise VotingError(
                    f'Agent {self.agent_id} LLM vote not in {candidates=}'
                )
            return target_id
        except ValueError as err:
            raise VotingError(
                f'Agent {self.agent_id} LLM vote response invalid: {err.__str__()}'
            )

    async def answer_question(self, content: str) -> str:
        """Generate answer to host question.

        Args:
            content: Question from the host.

        Returns:
            Generated answer text.

        TODO: test me

        """
        host_question_template = await self.db.get_system_prompt(
            key=SystemPromptKey.host_question_template
        )
        extra_prompt = host_question_template.format(content=content)
        text = await self._agent_message(
            extra_prompt,
            max_tokens=self.settings.message_max_tokens,
        )
        logger.info(f'Agent {self.agent_id} answered question: {text[:10]}...')
        return text

    async def _agent_message(self, request: LLMRequest) -> str:
        """Build prompt from given data and call ollama.

        Args:
            request (LLMRequest): data for request ollama.

        Returns:
            str: generated text from the LLM.

        TODO: test me

        """

        prompt = request.prompt()

        response = await self.ollama.generate(
            model=self.settings.ollama_model,
            prompt=prompt,
            options={'num_predict': request.max_tokens},
        )

        if response.response is None:
            logger.warning('Empty ollama response')

        return response.response if response.response else ''

    async def _agent_messages_summary(self) -> str:
        return ''
