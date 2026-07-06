import flet as ft
from dependency_injector.wiring import Provide, inject

from core.game import Game
from di_containers import Container


class GameControls:
    """Game control panel component.

    Provides start game button and event log display.

    """

    def __init__(
        self,
        on_game_started,  # type: ignore[no-untyped-def]
    ) -> None:
        self._on_game_started = on_game_started
        self._event_log: list[str] = []
        self._log_view = ft.ListView(
            spacing=4,
            padding=10,
            auto_scroll=True,
            height=200,
        )
        self._start_button = ft.ElevatedButton(
            '🚀 Start New Game',
            on_click=self._handle_start_game,  # type: ignore[arg-type]
            width=300,
        )

    def build(self) -> ft.Control:
        """Return Flet control for this component."""
        return ft.Column(
            controls=[
                ft.Text('🎮 Game Control', size=20, weight=ft.FontWeight.BOLD),
                self._start_button,
                ft.Divider(height=10),
                ft.Text('Event log (last 10 entries)', size=12),
                ft.Container(
                    content=self._log_view,
                    border=ft.Border.all(1, ft.Colors.OUTLINE),
                    border_radius=8,
                ),
            ],
            expand=True,
        )

    @inject
    async def _handle_start_game(
        self,
        e: ft.ControlEvent,
        game: Game = Provide[Container.game],
    ) -> None:
        """Handle start game button click to begin a game."""
        try:
            await game.begin_game()
            self.add_log_entry('Game started')
            await self._on_game_started()
            if e.page:
                e.page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text('New game started!'),
                        bgcolor=ft.Colors.GREEN,
                    )
                )
        except Exception as exc:
            if e.page:
                e.page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text(f'Error: {exc.__str__()}'),
                        bgcolor=ft.Colors.RED,
                    )
                )

    def add_log_entry(self, entry: str) -> None:
        """Add entry to event log."""
        self._event_log.append(entry)
        if len(self._event_log) > 10:
            self._event_log = self._event_log[-10:]

        self._log_view.controls = [
            ft.Text(f'• {e}', size=12) for e in reversed(self._event_log)
        ]
        self._log_view.update()
