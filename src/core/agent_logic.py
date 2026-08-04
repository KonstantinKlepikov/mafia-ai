from loguru import logger

from config import MafiaSettings
from core.llm import LLM
from data import Database
from schemas import (
    AgentRole,
    GamePhase,
    Message,
    MessageItem,
    MessageRequest,
    MessageRole,
    Persona,
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
        llm (LLM): direct local inference.
        db (Database): instance for state persistence.

    """

    def __init__(
        self,
        agent_id: int,
        persona: Persona,
        llm: LLM,
        db: Database,
        settings: MafiaSettings,
    ) -> None:
        self.agent_id = agent_id
        self.persona = persona
        self.llm = llm
        self.db = db
        self.settings = settings

    async def generate_message(self, phase: GamePhase, game_round: int) -> str:
        """Generate a message for the current phase.

        Args:
            phase: Current game phase (NIGHT or DAY).
            game_round: Current round number.

        Returns:
            Generated message text.

        TODO: test me

        """
        state = await self.db.get_agent_state(self.agent_id)
        if state.role != AgentRole.MAFIA:
            return ''

        hidden = True if phase == GamePhase.NIGHT else False

        extra_prompt = (
            await self.db.get_system_prompt(key=SystemPromptKey.night_speak)
            if hidden
            else await self.db.get_system_prompt(key=SystemPromptKey.day_speak)
        )
        logger.debug(f'Extra prompt text: {extra_prompt}')

        text = await self._generate_llm_response(
            extra_user_msg=extra_prompt,
            max_tokens=self.settings.message_max_tokens,
        )

        message = Message(
            sender_id=self.agent_id,
            content=text,
            phase=phase,
            round=game_round,
            target_audience=TargetAudience.MAFIA_ONLY if hidden else TargetAudience.ALL,
        )
        await self.db.insert_message(message=message)
        logger.info(f'Agent {self.agent_id} generated message for: {phase}')
        logger.debug(f'Message text: {text}')
        return text

    async def generate_vote(self, candidates: list[int], is_night: bool) -> int:
        """Generate a vote for elimination.

        Args:
            candidates (list[int]): alive agent IDs (excluding self).
            is_night (bool): True for night vote, False for day vote.

        Raises:
            ValueError: epty list of candidates
            VotingError: wrong llm voting

        Returns:
            Target agent ID to vote for.

        TODO: test me

        """
        if not candidates:
            raise ValueError('Empty list of candidates')

        vote_template = await self.db.get_system_prompt(
            key=SystemPromptKey.vote_template
        )

        extra_prompt = vote_template.format(
            vote_action='eliminate at night'
            if is_night
            else 'vote to eliminate during the day',
            candidates=', '.join(map(str, candidates)),
        )

        raw = await self._generate_llm_response(
            extra_user_msg=extra_prompt,
            max_tokens=self.settings.vote_max_tokens,
        )

        try:
            target_id = int(raw.strip())
            if target_id not in candidates:
                raise VotingError(
                    f'Agent {self.agent_id} LLM vote not in {candidates=}'
                )
            return target_id
        except Exception as ex:
            raise VotingError(
                f'Agent {self.agent_id} LLM vote response invalid: {ex.__str__()}'
            )

    async def answer_question(self, question_text: str) -> str:
        """Generate answer to host question.

        Args:
            question_text: Question from the host.

        Returns:
            Generated answer text.

        TODO: test me

        """
        host_question_template = await self.db.get_system_prompt(
            key=SystemPromptKey.host_question_template
        )
        extra_prompt = host_question_template.format(question_text=question_text)
        text = await self._generate_llm_response(
            extra_prompt,
            max_tokens=self.settings.message_max_tokens,
        )
        logger.info(f'Agent {self.agent_id} answered question: {text[:10]}...')
        return text

    async def _generate_llm_response(self, extra_user_msg: str, max_tokens: int) -> str:
        """Build context from history and call the LLM service.

        Args:
            extra_user_msg: Instruction appended as the final user turn.
            max_tokens: Upper bound on generated tokens.

        Returns:
            str: generated text from the LLM.

        TODO: test me

        """
        state = await self.db.get_agent_state(agent_id=self.agent_id)

        messages: list[MessageItem] = []
        for msg in state.message_history:
            if msg.sender_id == self.agent_id:
                messages.append(
                    MessageItem(role=MessageRole.ASSISTANT, content=msg.content)
                )
            else:
                messages.append(
                    MessageItem(
                        role=MessageRole.USER,
                        content=f'[{msg.sender_id}]: {msg.content}',
                    )
                )

        messages.append(MessageItem(role=MessageRole.USER, content=extra_user_msg))

        request = MessageRequest(
            system_prompt=self.persona.prompt,
            messages=messages,
            max_tokens=max_tokens,
        )

        return await self.llm.message(request=request)
