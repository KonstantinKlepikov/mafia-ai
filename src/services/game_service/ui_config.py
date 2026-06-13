from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminFletSettings(BaseSettings):
    """Settings for the Flet admin panel."""

    poll_interval_seconds: float = 2.0
    window_width: int = 1400
    window_height: int = 900

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
