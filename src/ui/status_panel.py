import flet as ft

from schemas import Agent, GameState


class StatusPanel:
    """Game status panel component.

    Displays current phase, round, and agent table.

    """

    def __init__(self) -> None:
        self._phase_text = ft.Text('—', size=18, weight=ft.FontWeight.BOLD)
        self._round_text = ft.Text('—', size=18, weight=ft.FontWeight.BOLD)
        self._alive_text = ft.Text('Alive: 0 | Eliminated: 0', size=12)
        self._agents_table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text('Agent')),
                ft.DataColumn(label=ft.Text('Role')),
                ft.DataColumn(label=ft.Text('Status')),
            ],
            rows=[],
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
        )
        self._agent_cache: dict[str, Agent] = {}

    def build(self) -> ft.Control:
        """Return Flet control for this component."""
        return ft.Column(
            controls=[
                ft.Text('📊 Status', size=20, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text('Phase:', size=14),
                                    self._phase_text,
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text('Round:', size=14),
                                    self._round_text,
                                ],
                                spacing=8,
                            ),
                            self._alive_text,
                            ft.Divider(height=10),
                            ft.Container(
                                content=self._agents_table,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=10,
                    border=ft.Border.all(1, ft.Colors.OUTLINE),
                    border_radius=8,
                    expand=True,
                ),
            ],
            expand=True,
        )

    def update_state(
        self,
        game_state: GameState | None,
        agents: dict[str, Agent],
    ) -> None:
        """Update status panel with new game state."""
        if game_state is None:
            self._phase_text.value = 'Offline'
            self._round_text.value = '—'
            self._alive_text.value = 'Orchestrator offline'
            self._agents_table.rows = []
        else:
            self._phase_text.value = game_state.phase.replace('_', ' ')
            self._round_text.value = str(game_state.round)
            self._alive_text.value = (
                f'Alive: {len(game_state.alive_agents)} | '
                f'Eliminated: {len(game_state.eliminated)}'
            )

            self._agent_cache.update(agents)
            all_ids = game_state.alive_agents + game_state.eliminated
            rows = []
            for agent_id in all_ids:
                if agent_id in self._agent_cache:
                    agent = self._agent_cache[agent_id]
                    status_icon = '✅' if agent_id in game_state.alive_agents else '💀'
                    rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(agent.persona_name)),
                                ft.DataCell(ft.Text(agent.role.value)),
                                ft.DataCell(ft.Text(status_icon)),
                            ]
                        )
                    )
            self._agents_table.rows = rows

        self._phase_text.update()
        self._round_text.update()
        self._alive_text.update()
        self._agents_table.update()

    def get_agent_cache(self) -> dict[str, Agent]:
        """Return cached agent information."""
        return self._agent_cache
