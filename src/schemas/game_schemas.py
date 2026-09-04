from pydantic import BaseModel, Field

from schemas.enums import (
    AgentStatus,
    GamePhase,
    HostDecisionAction,
    Role,
    TargetAudience,
)


class Message(BaseModel):
    """Message for agent conversation.

    Attrs:
        agent_id (int): sender identifier. System identifier is always 1
        content (str): message text
        phase (int): game phase when the message was sent
        round (int): round number (non-negative integer)
        target (TargetAudience): intended audience (ALL or MAFIA_ONLY).
            Default to TargetAudience.ALL

    """

    agent_id: int
    content: str
    phase: GamePhase
    round: int = Field(..., ge=0)
    target: TargetAudience = TargetAudience.ALL


class VoteEvent(BaseModel):
    """Vote event submitted by an agent.

    Attrs:
        agent_id (int): ID of the voting agent
        target_id (int): ID of the vote target
        phase (GamePhase): voting phase
        round (int): voting round

    """

    agent_id: int
    target_id: int
    phase: GamePhase
    round: int


class GameState(BaseModel):
    """Consolidated game state published by the orchestrator"""

    round: int = Field(..., ge=0, description='Current round number')
    phase: GamePhase = Field(..., description='Current game phase')
    alive: list[int] = Field(default_factory=list, description='Alive agents')
    eliminated: list[int] = Field(default_factory=list, description='Eliminated agents')
    mafia: list[int] = Field(default_factory=list, description='Alive mafia')
    citizen: list[int] = Field(default_factory=list, description='Alive citizen')


class AgentSummary(BaseModel):
    """Summarysation of agent messages and answerss"""

    agent_id: int = Field(..., description='Unique agent identifier')
    messages: str = Field('', description='Agent messages summarisations')
    questions: str = Field(
        '',
        description='Summarisations of questions to agent from player',
    )
    answers: str = Field('', description='Agent answers summarisations')


class AgentStateInit(BaseModel):
    """Agent state for initialisation.

    Attrs:
        role (Role): Game role of agent
        status (AgentStatus): game status of agent. Default to AgentStatus.ALIVE.
        persona_id (int): persona id (assigned at game start)

    """

    role: Role
    status: AgentStatus = AgentStatus.ALIVE
    persona_id: int


class AgentState(AgentStateInit):
    """Local agent state maintained inside the agent service.

    Attes:
        agent_id (int): agent identifier
        message_history (list[Message]): stores received and sent messages
            for the current game.

    TODO: message_hystory -> summary (AgentSummary)

    """

    agent_id: int
    message_history: list[Message] = []


class AgentSchema(BaseModel):
    """Agent information.

    Attrs:
        state (AgentState): agent state
        persona (Persona): persona data

    """

    state: AgentState
    persona: 'Persona'


class AgentCount(BaseModel):
    """Count of mafia nd citizen

    Attrs:
        mafia (int): Mafia count
        citizen (int): Citizen count

    """

    mafia: int
    citizen: int


class HostQuestion(BaseModel):
    """A question sent by the human host to a specific agent."""

    question_id: str = Field(..., description='Unique question identifier (UUID)')
    agent_id: int = Field(..., description='Numeric ID of the agent being asked')
    content: str = Field(..., description='Question text from the host')


class AgentAnswer(BaseModel):
    """An agent's answer to a host question."""

    question_id: str = Field(..., description='ID of the question being answered')
    agent_id: int = Field(..., description='Numeric ID of the answering agent')
    content: str = Field(..., description='Generated answer text')


class Persona(BaseModel):
    """Persona document retrieved."""

    persona_id: int = Field(..., description='Numeric persona id stored in DB')
    name: str = Field(..., description='Persona display name')
    persona_type: str = Field(..., description='Character archetype')
    prompt: str = Field(..., description='System prompt text for the LLM')


class HostDecision(BaseModel):
    """Decision from the human host submitted via the REST API.

    Used at HOST_DECISION phase to finalise day-vote results.

    """

    action: HostDecisionAction = Field(
        HostDecisionAction.NOTHING,
        description='Decision action',
    )
    target_id: int | None = Field(
        None,
        description='Agent to eliminate; required when action is OVERRIDE',
    )


class MessageItem(BaseModel):
    """Single message of agent.

    Attrs:

        agent_name (str): agent name
        content (str): message text

    """

    agent_name: str
    content: str


class LLMRequest(BaseModel):
    """Request for ollama model.

    Attrs:

        persona_prompt (str): Persona system prompt
        phase_prompt (str): Curent phase system prompt
        summary (str): Summarized conversation history for this pgase
        messages (list[MessageItem]): Last or important messages (context)
        max_tokens (int): maximum tokens for generation. Default to 512.

    """

    persona_prompt: str
    phase_prompt: str
    summary: str
    messages: list[MessageItem] = []
    max_tokens: int = 512

    def prompt(self) -> str:
        """Prompt for ollama generation

        TODO: test me

        """
        txt = (
            f'{self.persona_prompt}\n'
            f'{self.phase_prompt}\n'
            f'Твои воспоминания о предыдущих событиях: {self.summary}\n'
        )
        if self.messages:
            txt = (
                txt + 'Несколько запомнивщихся сообщений, сделанных другими игроками:\n'
            )
            for message in self.messages:
                txt = txt + f'{message.agent_name} сказал: {message.content}\n'
        return txt
