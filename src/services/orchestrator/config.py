from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Orchestrator service settings loaded from environment variables.

    Attrs:
        amqp_url: AMQP connection URL for RabbitMQ.
        unified_agent_url: Base URL for unified agent service.
        agent_count: Total number of agents in the game.
        mafia_count: Number of mafia agents to assign.
        phase_duration_seconds: Max duration per NIGHT / DAY speaking phase.
        vote_timeout_seconds: Timeout when waiting for all votes to arrive.

    """

    amqp_url: str

    unified_agent_url: str = 'http://unified-agent:8100'

    agent_count: int
    mafia_count: int

    phase_duration_seconds: int
    vote_timeout_seconds: int

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
