"""Main Flet application for Mafia-AI admin panel (unified version)."""

import asyncio

import flet as ft
from loguru import logger

from shared.models import AgentAnswer, Message, VoteEvent

from ..config import AdminFletSettings, MafiaServiceSettings
from ..core.event_bus import EventBus
from ..core.service import GameService
from ..llm.service import LLMService
from .ask_agent_panel import AskAgentPanel
from .event_adapter import EventAdapter, EventKind
from .game_controls import GameControls
from .host_decision_panel import HostDecisionPanel
from .message_feed import MessageFeed
from .service_adapter import GameServiceAdapter
from .status_panel import StatusPanel


class MafiaAdminApp:
    """Mafia-AI admin panel application (unified version).

    This version creates and manages LLMService, GameService and EventBus directly.

    Args:
        game_settings: Unified service configuration.
        ui_settings: UI configuration settings.

    """

    def __init__(
        self,
        game_settings: MafiaServiceSettings,
        ui_settings: AdminFletSettings,
    ) -> None:
        self._game_settings = game_settings
        self._ui_settings = ui_settings

        # Initialized in start()
        self._llm_service: LLMService | None = None
        self._event_bus: EventBus | None = None
        self._game_service: GameService | None = None
        self._client: GameServiceAdapter | None = None
        self._subscriber: EventAdapter | None = None

        self._message_feed = MessageFeed()
        self._status_panel = StatusPanel()

        self._game_controls: GameControls | None = None
        self._ask_agent_panel: AskAgentPanel | None = None
        self._host_decision_panel: HostDecisionPanel | None = None

        self._update_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._page: ft.Page | None = None

    async def start(self, page: ft.Page) -> None:
        """Initialize and start the application."""
        self._page = page
        page.title = '🃏 Mafia-AI — Game Host UI'
        page.theme_mode = ft.ThemeMode.DARK
        page.width = self._ui_settings.window_width
        page.height = self._ui_settings.window_height

        # Create LLMService
        self._llm_service = LLMService(self._game_settings)
        await self._llm_service.start()
        logger.info('LLMService started successfully')

        # Create EventBus and GameService
        self._event_bus = EventBus()
        self._game_service = GameService(
            self._game_settings, self._llm_service, event_bus=self._event_bus
        )

        # Start GameService
        try:
            await self._game_service.start()
            logger.info('GameService started successfully')
        except Exception as exc:
            logger.error(f'GameService failed to start: {exc}')
            raise

        # Create adapters
        self._client = GameServiceAdapter(self._game_service)
        self._subscriber = EventAdapter(self._event_bus)
        await self._subscriber.start()

        self._game_controls = GameControls(
            self._client,
            on_game_started=self._on_game_started,
        )
        self._ask_agent_panel = AskAgentPanel(
            self._client,
            get_agents_fn=self._status_panel.get_agent_cache,
        )
        self._host_decision_panel = HostDecisionPanel(
            self._client,
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
            controls=[self._game_controls.build()],
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

        if self._subscriber:
            await self._subscriber.stop()
        if self._client:
            await self._client.close()
        if self._game_service:
            await self._game_service.stop()
            logger.info('GameService stopped')
        if self._llm_service:
            await self._llm_service.stop()
            logger.info('LLMService stopped')
        logger.info('MafiaAdminApp stopped')

    async def _update_loop(self) -> None:
        """Main update loop for real-time updates."""
        while True:
            try:
                await asyncio.sleep(self._ui_settings.poll_interval_seconds)
                await self._update_ui()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f'Error in update loop: {exc}')

    async def _update_ui(self) -> None:
        """Update UI with latest data from game service and event bus."""
        if not self._client or not self._subscriber:
            return

        game_state = await self._client.get_state()
        agents = await self._client.get_agents()

        self._status_panel.update_state(game_state, agents)

        if self._ask_agent_panel:
            self._ask_agent_panel.update_agents(agents)

        if self._host_decision_panel:
            self._host_decision_panel.update_visibility(game_state, agents)

        events = self._subscriber.get_events()
        for event in events:
            try:
                if event.kind == EventKind.MESSAGE:
                    msg = Message.model_validate_json(event.raw)
                    self._message_feed.add_message(msg)
                elif event.kind == EventKind.VOTE:
                    vote = VoteEvent.model_validate_json(event.raw)
                    self._message_feed.add_vote(vote)
                elif event.kind == EventKind.ANSWER:
                    answer = AgentAnswer.model_validate_json(event.raw)
                    self._message_feed.add_answer(answer)
            except Exception as exc:
                logger.warning(f'Failed to parse event: {exc}')

    async def _on_game_started(self) -> None:
        """Handle game started event."""
        self._message_feed.clear()
        if self._game_controls:
            self._game_controls.add_log_entry('Game started')

    async def _on_host_decision(self, log_msg: str) -> None:
        """Handle host decision event."""
        if self._game_controls:
            self._game_controls.add_log_entry(log_msg)
