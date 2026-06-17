import flet as ft
from loguru import logger

from ui.main_app import MafiaAdminApp


def main() -> None:
    """Start the Flet UI application with unified service."""
    app = MafiaAdminApp()

    async def flet_main(page: ft.Page) -> None:
        """Flet application entry point."""
        try:
            await app.start(page)
            # Keep the page alive
            page.on_disconnect = lambda _: None
        except Exception as exc:
            logger.error(f'Failed to start MafiaAdminApp: {exc.__str__()}')
            raise

    ft.app(
        target=flet_main,
        view=ft.AppView.WEB_BROWSER,
        port=8550,
    )


if __name__ == '__main__':
    main()
