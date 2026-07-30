import flet as ft
from loguru import logger

from core.logging import setup_logging
from di_containers import Container
from ui.main_app import MafiaAdminApp


def main() -> None:
    """Start the Flet UI application with unified service."""
    setup_logging(level='INFO')

    container = Container()
    app = MafiaAdminApp()

    async def flet_main(page: ft.Page) -> None:
        """Flet application entry point."""
        try:
            await container.init_game_engine()
            await app.start(page)
            # Keep the page alive
            page.on_disconnect = lambda _: None
        except Exception as exc:
            logger.error(f'Failed to start MafiaAdminApp: {exc.__str__()}')
            raise

    ft.run(
        main=flet_main,
        view=ft.AppView.WEB_BROWSER,
        port=8550,
    )


if __name__ == '__main__':
    # container = Container()
    main()
