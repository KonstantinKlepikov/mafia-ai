from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MafiaSettings(BaseSettings):
    """Unified Mafia service settings - combines LLM and Game settings.

    Attrs:
        ollama_binary_path: Path to ollama binary (default: 'ollama' from PATH).
        ollama_model: Name of the model to use for generation.
        ollama_timeout: Timeout in seconds for each ollama subprocess call.
        llm_pool_size: Number of parallel model instances (0 = auto-detect).
        agent_count: Total number of agents in the game.
        mafia_count: Number of mafia agents to assign.
        phase_duration_seconds: Max duration per NIGHT / DAY speaking phase.
        vote_timeout_seconds: Timeout when waiting for all votes to arrive.
        db_yaml_path: Path to prompts.yaml config file.
        message_max_tokens: Max tokens for agent message generation.
        vote_max_tokens: Max tokens for vote generation.
        ui_enabled: Whether to enable Flet UI.
        ui_port: Port for Flet UI web server.

    """

    # LLM settings (formerly from LLMSettings)
    ollama_binary_path: str = 'ollama'
    ollama_model: str = 'llama3.1:8b'
    ollama_timeout: int = 120
    llm_pool_size: int = 0

    # Game settings (formerly from GameSettings)
    agent_count: int = 10
    mafia_count: int = 3
    phase_duration_seconds: int = 180
    vote_timeout_seconds: int = 60

    db_yaml_path: Path = Path('./config/prompts.yaml')
    message_max_tokens: int = 150
    vote_max_tokens: int = 50

    # UI settings
    ui_enabled: bool = True
    ui_port: int = 8550

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')


class AdminFletSettings(BaseSettings):
    """Settings for the Flet admin panel."""

    poll_interval_seconds: float = 0.1
    window_width: int = 1400
    window_height: int = 900

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
