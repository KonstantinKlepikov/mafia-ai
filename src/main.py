"""Main entry point for unified Mafia-AI Service.

Runs Flet UI application with integrated LLMService and GameService.
"""

import flet as ft
from loguru import logger

from .config import AdminFletSettings, MafiaServiceSettings
from .ui.main_app import MafiaAdminApp


def main() -> None:
    """Start the Flet UI application with unified service."""
    settings = MafiaServiceSettings()
    ui_settings = AdminFletSettings(
        poll_interval_seconds=settings.poll_interval_seconds,
    )

    app = MafiaAdminApp(settings, ui_settings)

    async def flet_main(page: ft.Page) -> None:
        """Flet application entry point."""
        try:
            await app.start(page)
            # Keep the page alive
            page.on_disconnect = lambda _: None
        except Exception as exc:
            logger.error(f'Failed to start MafiaAdminApp: {exc}')
            raise

    logger.info(f'Starting unified Mafia-AI service on port {settings.ui_port}')
    ft.app(
        target=flet_main,
        view=ft.AppView.WEB_BROWSER,
        port=settings.ui_port,
    )


if __name__ == '__main__':
    main()
