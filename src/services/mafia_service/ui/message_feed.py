"""Message feed UI component."""

import flet as ft

from shared.models import AgentAnswer, Message, TargetAudience, VoteEvent


class MessageFeed:
    """Real-time message feed component.

    Displays messages, votes, and answers in a scrollable list.

    """

    def __init__(self) -> None:
        self._feed_items: list[ft.Control] = []
        self._list_view = ft.ListView(
            spacing=8,
            padding=10,
            auto_scroll=True,
            expand=True,
        )
        self._container = ft.Container(
            content=self._list_view,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            expand=True,
        )

    def build(self) -> ft.Control:
        """Return Flet control for this component."""
        return ft.Column(
            controls=[
                ft.Text('💬 Message Feed', size=20, weight=ft.FontWeight.BOLD),
                self._container,
            ],
            expand=True,
        )

    def add_message(self, msg: Message) -> None:
        """Add message to feed."""
        icon = '🌙' if msg.target_audience == TargetAudience.MAFIA_ONLY else '☀️'
        item = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        f'{icon} Round-{msg.round} · {msg.phase.value}',
                        size=12,
                        color=ft.Colors.SECONDARY,
                    ),
                    ft.Text(
                        f'{msg.sender_id}: {msg.content}',
                        size=14,
                        selectable=True,
                    ),
                ],
                spacing=2,
            ),
            padding=8,
            border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER),
            border_radius=4,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
        )
        self._feed_items.append(item)
        self._list_view.controls = self._feed_items
        self._list_view.update()

    def add_vote(self, vote: VoteEvent) -> None:
        """Add vote to feed."""
        item = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        f'🗳️ Round-{vote.round} · {vote.phase.value.replace("_", " ")}',
                        size=12,
                        color=ft.Colors.SECONDARY,
                    ),
                    ft.Text(
                        f'{vote.voter_id} → {vote.target_id}',
                        size=14,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=2,
            ),
            padding=8,
            border=ft.Border.all(1, ft.Colors.PRIMARY_CONTAINER),
            border_radius=4,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
        )
        self._feed_items.append(item)
        self._list_view.controls = self._feed_items
        self._list_view.update()

    def add_answer(self, answer: AgentAnswer) -> None:
        """Add agent answer to feed."""
        item = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        f'💬 Answer · q:{answer.question_id[:8]}',
                        size=12,
                        color=ft.Colors.SECONDARY,
                    ),
                    ft.Text(
                        f'{answer.agent_id}: {answer.answer_text}',
                        size=14,
                        italic=True,
                    ),
                ],
                spacing=2,
            ),
            padding=8,
            border=ft.Border.all(1, ft.Colors.TERTIARY_CONTAINER),
            border_radius=4,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
        )
        self._feed_items.append(item)
        self._list_view.controls = self._feed_items
        self._list_view.update()

    def clear(self) -> None:
        """Clear all feed items."""
        self._feed_items.clear()
        self._list_view.controls = []
        self._list_view.update()
