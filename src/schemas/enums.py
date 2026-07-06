from enum import Enum


class SystemPromptKey(str, Enum):
    """Key for system_prompts table"""

    night_speak = 'night_speak'
    day_speak = 'day_speak'
    vote_template = 'vote_template'
    host_question_template = 'host_question_template'


class AgentRole(str, Enum):
    """Agent role in the game."""

    CITIZEN = 'CITIZEN'
    MAFIA = 'MAFIA'
    SYSTEM = 'SYSTEM'


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


class AgentStatus(str, Enum):
    """Current container/game status of an agent."""

    ALIVE = 'ALIVE'
    ELIMINATED = 'ELIMINATED'


class HostDecisionAction(str, Enum):
    """Possible actions a host can take at the HOST_DECISION phase."""

    APPROVE = 'APPROVE'
    REJECT = 'REJECT'
    OVERRIDE = 'OVERRIDE'
    NOTHING = 'NOTHING'
