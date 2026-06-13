from pydantic_settings import BaseSettings, SettingsConfigDict


class GameServiceSettings(BaseSettings):
    """Game Service settings - unified orchestrator and agent manager.

    Attrs:
        amqp_url: AMQP connection URL for RabbitMQ.
        llm_url: Base URL for the LLM service (MCP-compatible).
        agent_count: Total number of agents in the game.
        mafia_count: Number of mafia agents to assign.
        phase_duration_seconds: Max duration per NIGHT / DAY speaking phase.
        vote_timeout_seconds: Timeout when waiting for all votes to arrive.
        db_yaml_path: Path to prompts.yaml config file.
        message_max_tokens: Max tokens for agent message generation.
        vote_max_tokens: Max tokens for vote generation.

    """

    amqp_url: str
    llm_url: str

    agent_count: int
    mafia_count: int

    phase_duration_seconds: int
    vote_timeout_seconds: int

    db_yaml_path: str = '/app/config/prompts.yaml'
    message_max_tokens: int
    vote_max_tokens: int

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
