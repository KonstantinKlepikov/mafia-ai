"""Configuration for the LLM MCP service, loaded from environment variables."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM service settings.

    Attrs:
        ollama_url: Base URL of the Ollama REST server.
        ollama_model: Name of the model to use for generation.
        llm_queue_max_size: Maximum number of pending requests
            (legacy, for backward compat).
        llm_pool_size: Number of parallel model instances (0 = auto-detect).

    """

    ollama_url: HttpUrl = 'http://ollama:11434'  # type: ignore[assignment]
    ollama_model: str = 'llama3.1:8b'
    llm_queue_max_size: int = 100
    llm_pool_size: int = 0

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')


settings = LLMSettings()
