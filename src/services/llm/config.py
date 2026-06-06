"""Configuration for the LLM MCP service, loaded from environment variables."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    # Base URL of the Ollama REST server
    ollama_url: HttpUrl

    # Name of the model to use for generation
    ollama_model: str

    # Maximum number of pending requests in the rate-limiting queue.
    # Requests beyond this limit will block until a slot becomes available.
    llm_queue_max_size: int

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')


settings = LLMSettings()
