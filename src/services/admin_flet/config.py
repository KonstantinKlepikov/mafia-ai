"""Configuration settings for Admin Flet application."""

from pydantic_settings import BaseSettings


class AdminFletSettings(BaseSettings):
    """Settings for the Flet admin panel."""

    orchestrator_url: str = 'http://localhost:8081'
    amqp_url: str = 'amqp://guest:guest@localhost:5672/'
    poll_interval_seconds: float = 2.0
    window_width: int = 1400
    window_height: int = 900

    class Config:
        """Pydantic config."""

        env_prefix = 'ADMIN_FLET_'
