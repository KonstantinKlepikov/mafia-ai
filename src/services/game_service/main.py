"""Main entry point for Mafia-AI Game Service.

Runs Flet UI application with integrated GameService.
"""

import flet as ft
from loguru import logger

from .config import GameServiceSettings
from .ui.main_app import MafiaAdminApp
from .ui_config import AdminFletSettings


def main() -> None:
    """Start the Flet UI application."""
    game_settings = GameServiceSettings()
    ui_settings = AdminFletSettings(
        poll_interval_seconds=game_settings.poll_interval_seconds,
    )

    app = MafiaAdminApp(game_settings, ui_settings)

    async def flet_main(page: ft.Page) -> None:
        """Flet application entry point."""
        try:
            await app.start(page)
            # Keep the page alive
            page.on_disconnect = lambda _: None
        except Exception as exc:
            logger.error(f'Failed to start MafiaAdminApp: {exc}')
            raise

    logger.info(f'Starting Flet UI on port {game_settings.ui_port}')
    ft.app(
        target=flet_main,
        view=ft.AppView.WEB_BROWSER,
        port=game_settings.ui_port,
    )


if __name__ == '__main__':
    main()
