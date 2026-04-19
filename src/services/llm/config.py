"""Configuration for the LLM MCP service, loaded from environment variables."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    # Base URL of the Ollama REST server
    ollama_url: HttpUrl = HttpUrl('http://ollama:11434')

    # Name of the model to use for generation
    ollama_model: str = 'mistral'

    # Maximum number of pending requests in the rate-limiting queue.
    # Requests beyond this limit will block until a slot becomes available.
    llm_queue_max_size: int = 10

    # HTTP port the FastAPI service listens on
    llm_http_port: int = 8080

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')


settings = LLMSettings()
