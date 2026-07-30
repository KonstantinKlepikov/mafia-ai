from pydantic import BaseModel, Field

from schemas.enums import (
    AgentRole,
    AgentStatus,
    GamePhase,
    HostDecisionAction,
    TargetAudience,
)


class Message(BaseModel):
    """Message exchanged via the RabbitMQ broker.

    - `sender_id`: sender identifier. System identifier is always 1
    - `content`: message text
    - `phase`: game phase when the message was sent
    - `round`: round number (non-negative integer)
    - `target_audience`: intended audience (ALL or MAFIA_ONLY)

    """

    sender_id: int = Field(..., description='Sender ID, e.g. agent id')
    content: str = Field(..., description='Message text')
    phase: GamePhase = Field(..., description='Game phase when the message was sent')
    round: int = Field(..., ge=0, description='Round number (non-negative integer)')
    target_audience: TargetAudience = Field(
        TargetAudience.ALL,
        description='Intended audience (ALL or MAFIA_ONLY)',
    )


class VoteEvent(BaseModel):
    """Vote event submitted by an agent.

    Consumed by the orchestrator to tally votes.

    """

    voter_id: int = Field(..., description='ID of the voting agent')
    target_id: int = Field(..., description='ID of the vote target')
    phase: GamePhase = Field(
        ..., description='Phase in which the vote was cast (DAY_VOTE or NIGHT_VOTE)'
    )
    round: int = Field(..., ge=0, description='Round number of the vote')


class GameState(BaseModel):
    """Consolidated game state published by the orchestrator"""

    game_id: int = Field(..., ge=0, description='Current game ID')
    round: int = Field(..., ge=0, description='Current round number')
    phase: GamePhase = Field(..., description='Current game phase')
    alive: list[int] = Field(default_factory=list, description='Alive agents')
    eliminated: list[int] = Field(default_factory=list, description='Eliminated agents')


class AgentStateIn(BaseModel):
    """Agent state for initialisation.

    - 'role'
    - 'status'
    - 'persona_id'

    """

    role: AgentRole = Field(..., description='Game role (MAFIA or CITIZEN)')
    status: AgentStatus = Field(
        AgentStatus.ALIVE,
        description='Whether the agent is alive or eliminated',
    )
    persona_id: int = Field(
        ...,
        description='Persona ID (assigned at game start)',
    )


class AgentStateOut(AgentStateIn):
    """Local agent state maintained inside the agent service.

    - 'agent_id'
    - 'role'
    - 'status'
    - 'persona_id'
    - `message_history` stores received and sent messages for the current game.

    """

    agent_id: int = Field(..., description='Numeric unique agent identifier')
    message_history: list[Message] = Field(
        default_factory=list,
        description='History of messages received/sent in the current game',
    )


class Agent(BaseModel):
    """Agent information.

    - `state`: agent state
    - `persona`: persona data

    """

    state: AgentStateOut = Field(..., description='Agent state')
    persona: 'Persona' = Field(..., description='Persona data')


class AgentCount(BaseModel):
    """Count of mafia nd citizen"""

    mafia: int = Field(..., description='Mafia count')
    citizen: int = Field(..., description='Citizen count')


class HostQuestion(BaseModel):
    """A question sent by the human host to a specific agent.

    Published to routing key `host.question.{agent_id}` via RabbitMQ.

    """

    question_id: str = Field(..., description='Unique question identifier (UUID)')
    target_agent_id: int = Field(..., description='Numeric ID of the agent being asked')
    question_text: str = Field(..., description='Question text from the host')


class AgentAnswer(BaseModel):
    """An agent's answer to a host question.

    Published to routing key `host.answer.{question_id}` via RabbitMQ.

    """

    question_id: str = Field(..., description='ID of the question being answered')
    agent_id: int = Field(..., description='Numeric ID of the answering agent')
    answer_text: str = Field(..., description='Generated answer text')


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
