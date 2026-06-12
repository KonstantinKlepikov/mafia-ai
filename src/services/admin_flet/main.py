"""Main Flet application for Mafia-AI admin panel."""

import asyncio

import flet as ft
from admin_flet.config import AdminFletSettings
from admin_flet.core.client import AsyncOrchestratorClient
from admin_flet.core.subscriber import AsyncSubscriber, EventKind
from admin_flet.ui.ask_agent_panel import AskAgentPanel
from admin_flet.ui.game_controls import GameControls
from admin_flet.ui.host_decision_panel import HostDecisionPanel
from admin_flet.ui.message_feed import MessageFeed
from admin_flet.ui.status_panel import StatusPanel
from loguru import logger

from shared.models import AgentAnswer, Message, VoteEvent
from shared.telemetry import configure_loguru

configure_loguru('admin_flet')


class MafiaAdminApp:
    """Mafia-AI admin panel application."""

    def __init__(self, settings: AdminFletSettings) -> None:
        self._settings = settings
        self._client = AsyncOrchestratorClient(settings.orchestrator_url)
        self._subscriber = AsyncSubscriber(settings.amqp_url)

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
        page.width = self._settings.window_width
        page.height = self._settings.window_height

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

        await self._subscriber.stop()
        await self._client.close()
        logger.info('MafiaAdminApp stopped')

    async def _update_loop(self) -> None:
        """Main update loop for real-time updates."""
        while True:
            try:
                await asyncio.sleep(self._settings.poll_interval_seconds)
                await self._update_ui()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f'Error in update loop: {exc}')

    async def _update_ui(self) -> None:
        """Update UI with latest data from orchestrator and subscriber."""
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


async def main(page: ft.Page) -> None:
    """Main entry point for Flet application."""
    settings = AdminFletSettings()
    app = MafiaAdminApp(settings)

    try:
        await app.start(page)
        page.on_disconnect = lambda _: asyncio.create_task(app.stop())
    except Exception as exc:
        logger.error(f'Failed to start app: {exc}')
        raise


def run() -> None:
    """Run the Flet application."""
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8550)


if __name__ == '__main__':
    run()
