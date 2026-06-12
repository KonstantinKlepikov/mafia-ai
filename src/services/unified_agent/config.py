from pydantic_settings import BaseSettings, SettingsConfigDict


class UnifiedAgentSettings(BaseSettings):
    """Unified Agent service settings loaded from environment variables.

    Attrs:
        llm_url: Base URL for the LLM service (MCP-compatible).
        db_yaml_path: Path to prompts.yaml config file.
        message_max_tokens: Max tokens for agent message generation.
        vote_max_tokens: Max tokens for vote generation.

    """

    llm_url: str
    db_yaml_path: str = '/app/config/prompts.yaml'
    message_max_tokens: int
    vote_max_tokens: int

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
