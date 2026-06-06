"""Settings for the admin panel service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    """Admin panel configuration loaded from environment variables.

    Attrs:
        amqp_url: AMQP connection URL for RabbitMQ.
        orchestrator_url: Base URL of the orchestrator REST API.

    """

    amqp_url: str
    orchestrator_url: str

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
