import asyncio

import flet as ft
from dependency_injector.wiring import Provide, inject
from loguru import logger

from config import AdminFletSettings, MafiaSettings
from core.game import Game
from di_containers import Container
from schemas import AgentAnswer, Message, VoteEvent

from .ask_agent_panel import AskAgentPanel
from .game_controls import GameControls
from .host_decision_panel import HostDecisionPanel
from .message_feed import MessageFeed
from .status_panel import StatusPanel


class MafiaAdminApp:
    """Mafia-AI admin panel application (unified version).

    This version creates and manages LLM, Game and EventBus directly.

    Args:
        settings: game service configuration.
        ui_settings: UI configuration settings.

    """

    _game_controls: GameControls
    _ask_agent_panel: AskAgentPanel
    _host_decision_panel: HostDecisionPanel
    _update_task: asyncio.Task
    _page: ft.Page
    _message_feed: MessageFeed
    _status_panel: StatusPanel

    @inject
    def __init__(
        self,
        settings: MafiaSettings = Provide[Container.settings],
        ui_settings: AdminFletSettings = Provide[Container.ui_settings],
        game: Game = Provide[Container.game],
    ) -> None:
        self.settings = settings
        self.ui_settings = ui_settings
        self.game: Game = game

    async def start(self, page: ft.Page) -> None:
        """Initialize and start the application."""
        self._page = page
        page.title = '🃏 Mafia-AI — Game Host UI'
        page.theme_mode = ft.ThemeMode.DARK
        page.width = self.ui_settings.window_width
        page.height = self.ui_settings.window_height

        self._message_feed = MessageFeed()
        self._status_panel = StatusPanel()

        self.game_controls = GameControls(on_game_started=self._on_game_started)
        self._ask_agent_panel = AskAgentPanel(
            get_agents_fn=self._status_panel.get_agent_cache
        )
        self._host_decision_panel = HostDecisionPanel(
            get_agents_fn=self._status_panel.get_agent_cache,
            on_decision_fn=self._on_host_decision,
        )

        col_feed = ft.Column(
            controls=[self._message_feed.build()],
            expand=3,
        )
        col_status = ft.Column(
            controls=[self._status_panel.build()],
            expand=1,
        )
        row_main = ft.Row(
            controls=[col_feed, col_status],
            expand=True,
            spacing=10,
        )

        col_controls = ft.Column(
            controls=[self.game_controls.build()],
            expand=1,
        )
        col_ask = ft.Column(
            controls=[self._ask_agent_panel.build()],
            expand=1,
        )
        row_bottom = ft.Row(
            controls=[col_controls, col_ask],
            spacing=10,
        )

        page.add(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            '🃏 Mafia-AI — Game Host UI',
                            size=28,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Divider(height=10),
                        row_main,
                        self._host_decision_panel.build(),
                        ft.Divider(height=10),
                        row_bottom,
                    ],
                    spacing=10,
                    expand=True,
                ),
                padding=20,
                expand=True,
            )
        )

        self._update_task = asyncio.create_task(self._update_loop())
        logger.info('MafiaAdminApp started')

    async def stop(self) -> None:
        """Stop the application and cleanup resources."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info('MafiaAdminApp stopped')

    async def _update_loop(self) -> None:
        """Main update loop for real-time updates."""
        while True:
            try:
                await asyncio.sleep(self.ui_settings.poll_interval_seconds)
                if self.game.game_active:
                    await self._update_ui()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f'Error in update loop: {exc.__str__()}')

    async def _update_ui(self) -> None:
        """Update UI with latest data from game service and event bus."""

        game_state = await self.game.db.get_game_state(game_id=self.game.shared.game_id)
        agents = await self.game.get_alive_agents()

        self._status_panel.update_state(game_state=game_state, agents=agents)

        if self._ask_agent_panel:
            self._ask_agent_panel.update_agents(agents=agents)

        if self._host_decision_panel:
            self._host_decision_panel.update_visibility(
                game_state=game_state,
                agents=agents,
            )

        feed = self.game.event_bus.get()
        if feed is None:
            return
        elif isinstance(feed, Message):
            self._message_feed.add_message(feed)
        elif isinstance(feed, VoteEvent):
            self._message_feed.add_vote(feed)
        elif isinstance(feed, AgentAnswer):
            self._message_feed.add_answer(feed)

    async def _on_game_started(self) -> None:
        """Handle game started event."""
        self._message_feed.clear()
        if self.game_controls:
            self.game_controls.add_log_entry('Game started')

    async def _on_host_decision(self, log_msg: str) -> None:
        """Handle host decision event."""
        if self.game_controls:
            self.game_controls.add_log_entry(log_msg)
