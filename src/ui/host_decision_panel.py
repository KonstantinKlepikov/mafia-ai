import flet as ft
from dependency_injector.wiring import Provide, inject

from core.service import Game
from di_containers import Container
from shared.models import Agent, GameState, HostDecision, HostDecisionAction


class HostDecisionPanel:
    """Host decision panel component.

    Shown only during HOST_DECISION phase.
    Provides Approve/Reject/Override buttons.

    """

    def __init__(
        self,
        get_agents_fn,  # type: ignore[no-untyped-def]
        on_decision_fn,  # type: ignore[no-untyped-def]
    ) -> None:
        # self._client = client
        self._get_agents_fn = get_agents_fn
        self._on_decision_fn = on_decision_fn
        self._visible = False

        self._override_dropdown = ft.Dropdown(
            label='Override target',
            width=200,
            options=[],
        )
        self._approve_button = ft.ElevatedButton(
            '✅ Approve',
            on_click=self._handle_approve,  # type: ignore[arg-type]
            bgcolor=ft.Colors.GREEN,
            color=ft.Colors.WHITE,
        )
        self._reject_button = ft.ElevatedButton(
            '❌ Reject',
            on_click=self._handle_reject,  # type: ignore[arg-type]
        )
        self._override_button = ft.ElevatedButton(
            '🔁 Override',
            on_click=self._handle_override,  # type: ignore[arg-type]
        )

        self._container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        '⚖️ Host Decision Required',
                        size=20,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Container(
                        content=ft.Text(
                            'Phase: HOST_DECISION — choose an action below',
                            size=14,
                            color=ft.Colors.ORANGE,
                        ),
                        bgcolor=ft.Colors.ORANGE_100,
                        padding=10,
                        border_radius=8,
                    ),
                    ft.Row(
                        controls=[
                            self._approve_button,
                            self._reject_button,
                            self._override_dropdown,
                            self._override_button,
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=10,
            ),
            padding=10,
            border=ft.Border.all(2, ft.Colors.ORANGE),
            border_radius=8,
            visible=False,
        )

    def build(self) -> ft.Control:
        """Return Flet control for this component."""
        return self._container

    def update_visibility(
        self,
        game_state: GameState | None,
        agents: dict[str, Agent],
    ) -> None:
        """Update panel visibility based on game phase."""
        should_show = game_state is not None and game_state.phase == 'HOST_DECISION'

        if should_show:
            self._override_dropdown.options = [
                ft.DropdownOption(
                    key=agent_id,
                    text=f'{agent_id} · {agent.persona_name}',
                )
                for agent_id, agent in agents.items()
            ]
            if self._override_dropdown.value not in agents:
                self._override_dropdown.value = (
                    list(agents.keys())[0] if agents else None
                )
            self._override_dropdown.update()

        self._container.visible = should_show
        self._container.update()

    @inject
    async def _send_decision(
        self,
        decision: HostDecision,
        log_msg: str,
        success_msg: str,
        page: ft.BasePage | None,
        game: Game = Provide[Container.game],
    ) -> None:
        """Send decision to orchestrator."""
        try:
            game.submit_host_decision(decision)
            await self._on_decision_fn(log_msg)
            if page:
                page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text(success_msg),
                        bgcolor=ft.Colors.GREEN,
                    )
                )
        except Exception as exc:
            if page:
                page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text(f'Error: {exc.__str__()}'),
                        bgcolor=ft.Colors.RED,
                    )
                )

    async def _handle_approve(self, e: ft.ControlEvent) -> None:
        """Handle approve button click."""
        await self._send_decision(
            HostDecision(action=HostDecisionAction.APPROVE),
            'Host: APPROVED majority vote',
            'Sent: APPROVE',
            e.page,
        )

    async def _handle_reject(self, e: ft.ControlEvent) -> None:
        """Handle reject button click."""
        await self._send_decision(
            HostDecision(action=HostDecisionAction.REJECT),
            'Host: REJECTED elimination',
            'Sent: REJECT',
            e.page,
        )

    async def _handle_override(self, e: ft.ControlEvent) -> None:
        """Handle override button click."""
        target_id = self._override_dropdown.value
        if not target_id:
            if e.page:
                e.page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text('Please select override target'),
                        bgcolor=ft.Colors.ORANGE,
                    )
                )
            return

        await self._send_decision(
            HostDecision(action=HostDecisionAction.OVERRIDE, target_id=target_id),
            f'Host: OVERRIDE → {target_id}',
            f'Sent: OVERRIDE → {target_id}',
            e.page,
        )
