import flet as ft
from dependency_injector.wiring import Provide, inject

from core.service import Game
from di_containers import Container
from shared.models import Agent


class AskAgentPanel:
    """Ask agent panel component.

    Allows host to send questions to agents.

    """

    def __init__(
        self,
        get_agents_fn,  # type: ignore[no-untyped-def]
    ) -> None:
        self._get_agents_fn = get_agents_fn
        self._agent_dropdown = ft.Dropdown(
            label='Agent',
            width=300,
            options=[],
        )
        self._question_field = ft.TextField(
            label='Question',
            multiline=True,
            min_lines=3,
            max_lines=5,
            width=300,
            hint_text='Are you mafia?',
        )
        self._ask_button = ft.ElevatedButton(
            '📨 Ask',
            on_click=self._handle_ask,  # type: ignore[arg-type]
            width=300,
        )

    def build(self) -> ft.Control:
        """Return Flet control for this component."""
        return ft.Column(
            controls=[
                ft.Text('❓ Ask Agent', size=20, weight=ft.FontWeight.BOLD),
                self._agent_dropdown,
                self._question_field,
                self._ask_button,
            ],
            expand=True,
        )

    def update_agents(self, agents: dict[str, Agent]) -> None:
        """Update available agents dropdown."""
        if not agents:
            self._agent_dropdown.options = []
            self._agent_dropdown.value = None
        else:
            self._agent_dropdown.options = [
                ft.DropdownOption(
                    key=agent_id,
                    text=f'{agent_id} · {agent.persona_name}',
                )
                for agent_id, agent in agents.items()
            ]
            if self._agent_dropdown.value not in agents:
                self._agent_dropdown.value = list(agents.keys())[0] if agents else None

        self._agent_dropdown.update()

    @inject
    async def _handle_ask(
        self,
        e: ft.ControlEvent,
        game: Game = Provide[Container.game],
    ) -> None:
        """Handle ask button click."""
        agent_id = self._agent_dropdown.value
        question = self._question_field.value

        if not agent_id or not question or not question.strip():
            if e.page:
                e.page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text('Please select agent and enter question'),
                        bgcolor=ft.Colors.ORANGE,
                    )
                )
            return

        try:
            await game.ask_agent(agent_id, question.strip())
            self._question_field.value = ''
            self._question_field.update()

            if e.page:
                e.page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text('Question sent! Answer will appear in feed.'),
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
