from pydantic_settings import BaseSettings, SettingsConfigDict


class GameServiceSettings(BaseSettings):
    """Game Service settings - unified orchestrator and agent manager.

    Attrs:
        llm_url: Base URL for the LLM service (MCP-compatible).
        agent_count: Total number of agents in the game.
        mafia_count: Number of mafia agents to assign.
        phase_duration_seconds: Max duration per NIGHT / DAY speaking phase.
        vote_timeout_seconds: Timeout when waiting for all votes to arrive.
        db_yaml_path: Path to prompts.yaml config file.
        message_max_tokens: Max tokens for agent message generation.
        vote_max_tokens: Max tokens for vote generation.
        ui_enabled: Whether to enable Flet UI.
        ui_port: Port for Flet UI web server.
        poll_interval_seconds: UI update loop interval.

    """

    llm_url: str

    agent_count: int
    mafia_count: int

    phase_duration_seconds: int
    vote_timeout_seconds: int

    db_yaml_path: str = '/app/config/prompts.yaml'
    message_max_tokens: int
    vote_max_tokens: int

    # UI settings
    ui_enabled: bool = True
    ui_port: int = 8550
    poll_interval_seconds: float = 2.0

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
