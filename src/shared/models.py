"""Shared Pydantic models for the mafia-ai project.

Contains types for roles, phases, messages, vote events,
game/agent state, and host-agent Q&A interaction.
"""

from enum import Enum

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Agent role in the game.

    - `CITIZEN` — regular townsperson
    - `MAFIA` — mafia member

    """

    CITIZEN = 'CITIZEN'
    MAFIA = 'MAFIA'


class GamePhase(str, Enum):
    """Game cycle phase.

    Includes intermediate states for voting rounds and game-over.

    """

    NIGHT = 'NIGHT'
    NIGHT_VOTE = 'NIGHT_VOTE'
    RESOLVE_NIGHT = 'RESOLVE_NIGHT'
    DAY = 'DAY'
    DAY_VOTE = 'DAY_VOTE'
    HOST_DECISION = 'HOST_DECISION'
    GAME_OVER = 'GAME_OVER'


class TargetAudience(str, Enum):
    """Intended audience for a message.

    - `ALL`: all living agents
    - `MAFIA_ONLY`: mafia members only

    """

    ALL = 'ALL'
    MAFIA_ONLY = 'MAFIA_ONLY'


class Message(BaseModel):
    """Message exchanged via the RabbitMQ broker.

    - `sender_id`: sender identifier, e.g. `agent-1` or `system`
    - `content`: message text
    - `phase`: game phase when the message was sent
    - `round`: round number (non-negative integer)
    - `target_audience`: intended audience (ALL or MAFIA_ONLY)
    - `metadata`: optional free-form extra data

    TODO: more concrete and typed metadata

    """

    sender_id: str = Field(..., description="Sender ID, e.g. 'agent-1' or 'system'")
    content: str = Field(..., description='Message text')
    phase: GamePhase = Field(..., description='Game phase when the message was sent')
    round: int = Field(..., ge=0, description='Round number (non-negative integer)')
    target_audience: TargetAudience = Field(
        TargetAudience.ALL,
        description='Intended audience (ALL or MAFIA_ONLY)',
    )
    metadata: dict | None = Field(None, description='Optional free-form extra data')


class VoteEvent(BaseModel):
    """Vote event submitted by an agent.

    Consumed by the orchestrator to tally votes.

    """

    voter_id: str = Field(..., description='ID of the voting agent')
    target_id: str = Field(..., description='ID of the vote target')
    phase: GamePhase = Field(
        ..., description='Phase in which the vote was cast (DAY_VOTE or NIGHT_VOTE)'
    )
    round: int = Field(..., ge=0, description='Round number of the vote')


class GameState(BaseModel):
    """Consolidated game state published by the orchestrator.

    - `alive_agents`: IDs of agents still in the game.
    - `eliminated`: IDs of agents who have been removed.

    """

    round: int = Field(..., ge=0, description='Current round number')
    phase: GamePhase = Field(..., description='Current game phase')
    alive_agents: list[str] = Field(
        default_factory=list, description='IDs of living agents'
    )
    eliminated: list[str] = Field(
        default_factory=list, description='IDs of eliminated agents'
    )


class AgentState(BaseModel):
    """Local agent state maintained inside the agent service.

    - `persona_id` references a VectorDB entry holding the agent's system prompt.
    - `message_history` stores received and sent messages for the current game.

    """

    agent_id: str = Field(..., description='Unique agent identifier')
    role: AgentRole = Field(..., description='Game role (MAFIA or CITIZEN)')
    persona_id: str | None = Field(
        None,
        description='Persona ID in VectorDB (assigned at game start)',
    )
    message_history: list[Message] = Field(
        default_factory=list,
        description='History of messages received/sent in the current game',
    )


class AgentStatus(str, Enum):
    """Current container/game status of an agent."""

    ALIVE = 'ALIVE'
    ELIMINATED = 'ELIMINATED'


class AgentInfo(BaseModel):
    """Agent information returned by the agent's HTTP API and used by the orchestrator.

    - `agent_id`: unique agent identifier
    - `persona_name`: display name from VectorDB persona
    - `role`: game role (MAFIA or CITIZEN); exposed to the orchestrator and admin panel
    - `status`: whether the agent is alive or eliminated
    - `container_id`: Docker container ID; used by the orchestrator
      to stop the container

    """

    agent_id: str = Field(..., description='Unique agent identifier')
    persona_name: str = Field(..., description='Display name from the VectorDB persona')
    role: AgentRole = Field(..., description='Game role (MAFIA or CITIZEN)')
    status: AgentStatus = Field(
        AgentStatus.ALIVE,
        description='Whether the agent is alive or eliminated',
    )
    container_id: str | None = Field(
        None,
        description='Docker container ID for orchestrator-side container management',
    )


class HostQuestion(BaseModel):
    """A question sent by the human host to a specific agent.

    Published to routing key `host.question.{agent_id}` via RabbitMQ.

    """

    question_id: str = Field(..., description='Unique question identifier (UUID)')
    target_agent_id: str = Field(..., description='ID of the agent being asked')
    question_text: str = Field(..., description='Question text from the host')


class AgentAnswer(BaseModel):
    """An agent's answer to a host question.

    Published to routing key `host.answer.{question_id}` via RabbitMQ.

    """

    question_id: str = Field(..., description='ID of the question being answered')
    agent_id: str = Field(..., description='ID of the answering agent')
    answer_text: str = Field(..., description='Generated answer text')
