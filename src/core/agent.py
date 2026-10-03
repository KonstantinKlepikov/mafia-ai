from loguru import logger
from ollama import AsyncClient

from config import MafiaSettings
from core.crud import Database
from schemas import (
    GamePhase,
    GameState,
    LLMRequest,
    Message,
    Persona,
    Role,
    SystemPromptKey,
    TargetAudience,
    VotingError,
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
        role: Role,
        persona: Persona,
        prompts: dict[SystemPromptKey, str],
        db: Database,
        ollama: AsyncClient,
        settings: MafiaSettings,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.persona = persona
        self.prompts = prompts
        self.db = db
        self.settings = settings
        self.ollama = ollama

    async def _request(self, phase_prompt: str, summary: str) -> LLMRequest:
        """Make lllm request

        Args:
            phase_prompt (str): prompt for this phase

        Returns:
            LLMRequest: request

        TODO: test me
        TODO: concurent

        """
        # TODO: move limit to config
        messages = await self.db.get_last_conversation(limit=10)
        return LLMRequest(
            system_prompt=self.prompts[SystemPromptKey.system_prompt],
            persona_name=self.persona.name,
            role=self.role,
            persona_character=self.persona.persona_type,
            persona_prompt=self.persona.prompt,
            phase_prompt=phase_prompt,
            summary=summary,
            messages=messages,
            max_tokens=self.settings.message_max_tokens,
        )

    async def _message_to_db(
        self,
        game_state: GameState,
        text: str,
        target: TargetAudience,
    ) -> None:
        """Stor message to db

        Args:
            game_state (GameState): Current game state.
            text (str): message text
            target (TargetAudience): target audience

        TODO: test me

        """
        message = Message(
            agent_id=self.agent_id,
            content=text,
            phase=game_state.phase,
            round=game_state.round,
            target=target,
        )
        await self.db.insert_message(message=message)
        logger.info(f'Agent {self.agent_id} generated message for: {game_state.phase}')

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
            self.prompts[SystemPromptKey.night_speak]
            if hidden
            else self.prompts[SystemPromptKey.day_speak]
        )
        summary = await self.db.get_agent_summary(agent_id=self.agent_id)

        # TODO: here we need summary of all conversations
        # (for mafia full, for citizen sequenced)
        request = await self._request(
            phase_prompt=phase_prompt,
            summary=summary.messages,
        )

        text = await self._generate(request=request)
        await self._message_to_db(
            game_state=game_state,
            text=text,
            target=TargetAudience.MAFIA_ONLY if hidden else TargetAudience.ALL,
        )

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
        candidates = (
            game_state.citizen
            if game_state.phase == GamePhase.NIGHT_VOTE
            else game_state.alive
        )

        phase_prompt = self.prompts[SystemPromptKey.vote_template].format(
            vote_action='eliminate at night'
            if game_state.phase == GamePhase.NIGHT_VOTE
            else 'vote to eliminate during the day',
            candidates=', '.join(map(str, candidates)),
        )

        summary = await self.db.get_agent_summary(agent_id=self.agent_id)

        # TODO: here we need summary of all conversations
        # (for mafia full, for citizen sequenced)
        request = await self._request(
            phase_prompt=phase_prompt,
            summary=summary.messages,
        )

        target_id = await self._generate(request=request)

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
        extra_prompt = self.prompts[SystemPromptKey.host_question_template].format(
            content=content
        )
        text = await self._generate(
            extra_prompt,
            max_tokens=self.settings.message_max_tokens,
        )
        logger.info(f'Agent {self.agent_id} answered question: {text[:10]}...')
        return text

    async def _generate(self, request: LLMRequest) -> str:
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

    async def _generates_summary(self) -> str:
        return ''
