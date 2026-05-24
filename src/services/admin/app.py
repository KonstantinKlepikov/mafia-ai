"""Streamlit admin panel for the Mafia-AI game host.

Provides real-time visibility into the game via RabbitMQ subscription
and full host-control capabilities via the Orchestrator REST API.

Layout (refreshes every 2 s via ``@st.fragment(run_every=2)``):

    ┌───────────────────────────┬─────────────┐
    │  💬 Message Feed          │ 📊 Status   │
    │                           │             │
    ├───────────────────────────┴─────────────┤
    │  ⚖️ Host Decision  (HOST_DECISION only) │
    ├────────────────────┬────────────────────┤
    │  🎮 Game Control   │  ❓ Ask Agent      │
    └────────────────────┴────────────────────┘
"""

import pandas as pd
import streamlit as st
from admin.config import AdminSettings
from admin.core import subscriber as sub
from admin.core.client import OrchestratorClient, OrchestratorClientError

from shared.models import (
    AgentAnswer,
    AgentInfo,
    GamePhase,
    GameState,
    HostDecision,
    HostDecisionAction,
    Message,
    TargetAudience,
    VoteEvent,
)
from shared.telemetry import configure_loguru

configure_loguru('admin')

# ── Page config (must be the first st.* call) ─────────────────────────
st.set_page_config(page_title='Mafia-AI Admin', layout='wide', page_icon='🃏')


# ── One-time resource init (cached across all sessions and reruns) ─────
@st.cache_resource
def _get_client() -> OrchestratorClient:
    """Initialise the orchestrator client and start the RabbitMQ subscriber."""
    settings = AdminSettings()
    sub.ensure_started(settings.amqp_url)
    return OrchestratorClient(settings.orchestrator_url)


# ── Helpers ───────────────────────────────────────────────────────────


def _parse_event(ev: sub.FeedEvent) -> tuple[str, object] | None:
    """Parse a raw RabbitMQ event into a (kind, model) feed entry."""
    if ev.kind == sub.EventKind.MESSAGE:
        return ('message', Message.model_validate_json(ev.raw))
    if ev.kind == sub.EventKind.ANSWER:
        return ('answer', AgentAnswer.model_validate_json(ev.raw))
    if ev.kind == sub.EventKind.VOTE:
        return ('vote', VoteEvent.model_validate_json(ev.raw))
    return None


def _init_session_state() -> None:
    """Initialise session-state keys on first run."""
    defaults: dict[str, object] = {
        'feed': [],
        'event_log': [],
        'msg_index': 0,
        'agent_cache': {},
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _drain_queue() -> None:
    """Pull new RabbitMQ events into ``st.session_state['feed']``."""
    _init_session_state()
    new_events, new_index = sub.get_events_from(st.session_state['msg_index'])
    st.session_state['msg_index'] = new_index
    for ev in new_events:
        try:
            parsed = _parse_event(ev)
            if parsed is not None:
                st.session_state['feed'].append(parsed)
        except Exception:
            pass


def _render_feed() -> None:
    """7.1 — Real-time message feed."""
    st.subheader('💬 Message Feed')
    feed: list[tuple[str, object]] = st.session_state.get('feed', [])
    if not feed:
        st.info('No messages yet. Start a game to see messages here.')
        return

    for kind, item in feed[-60:]:
        if kind == 'message':
            msg: Message = item  # type: ignore[assignment]
            icon = '🌙' if msg.target_audience == TargetAudience.MAFIA_ONLY else '☀️'
            st.markdown(
                f'{icon} **[R{msg.round} · {msg.phase.value}]** '
                f'`{msg.sender_id}`: {msg.content}'
            )
        elif kind == 'answer':
            ans: AgentAnswer = item  # type: ignore[assignment]
            st.markdown(f'💬 **[Host Q&A]** `{ans.agent_id}`: {ans.answer_text}')
        elif kind == 'vote':
            vote: VoteEvent = item  # type: ignore[assignment]
            st.markdown(
                f'🗳️ **[Vote · {vote.phase.value}]** '
                f'`{vote.voter_id}` → `{vote.target_id}`'
            )


def _render_status(
    game_state: GameState | None,
    agents: dict[str, AgentInfo],
) -> None:
    """7.2 — Status panel: phase, round, agent table."""
    st.subheader('📊 Status')

    if game_state is None:
        st.warning('Orchestrator offline')
        return

    st.metric('Phase', game_state.phase.replace('_', ' '))
    st.metric('Round', str(game_state.round))
    st.caption(
        f'Alive: {len(game_state.alive_agents)} | '
        f'Eliminated: {len(game_state.eliminated)}'
    )

    # Merge live poll with session cache so eliminated agents keep their names.
    cache: dict[str, AgentInfo] = st.session_state.get('agent_cache', {})
    cache.update(agents)
    st.session_state['agent_cache'] = cache

    all_ids = game_state.alive_agents + game_state.eliminated
    rows = [
        {
            'Agent': cache[a].persona_name if a in cache else a,
            'Role': cache[a].role.value if a in cache else '?',
            'Status': '✅' if a in game_state.alive_agents else '💀',
        }
        for a in all_ids
    ]
    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=min(len(rows) * 35 + 40, 420),
        )


def _send_decision(
    client: OrchestratorClient,
    decision: HostDecision,
    log_msg: str,
    success_msg: str,
) -> None:
    """Submit a host decision and update the event log."""
    try:
        client.post_decision(decision)
        st.session_state['event_log'].append(log_msg)
        st.success(success_msg)
    except OrchestratorClientError as exc:
        st.error(str(exc))


def _render_override_col(
    game_state: GameState,
    client: OrchestratorClient,
) -> None:
    """Render the override column inside the host decision panel."""
    cache: dict[str, AgentInfo] = st.session_state.get('agent_cache', {})
    options = [
        f'{a} · {cache[a].persona_name}' if a in cache else a
        for a in game_state.alive_agents
    ]
    selected = st.selectbox('Override target', options, key='override_sel')
    if st.button('🔁 Override', use_container_width=True, key='btn_override'):
        if selected:
            target_id = selected.split(' ')[0]
            _send_decision(
                client,
                HostDecision(action=HostDecisionAction.OVERRIDE, target_id=target_id),
                f'Host: OVERRIDE → {target_id}',
                f'Sent: OVERRIDE → {target_id}',
            )


def _render_host_decision(
    game_state: GameState,
    client: OrchestratorClient,
) -> None:
    """7.3 — Host decision interface, shown only in HOST_DECISION phase."""
    st.divider()
    st.subheader('⚖️ Host Decision Required')
    st.warning('Phase: HOST_DECISION — choose an action below.')

    col_approve, col_reject, col_override = st.columns(3)

    with col_approve:
        if st.button(
            '✅ Approve',
            use_container_width=True,
            type='primary',
            key='btn_approve',
        ):
            _send_decision(
                client,
                HostDecision(action=HostDecisionAction.APPROVE),
                'Host: APPROVED majority vote',
                'Sent: APPROVE',
            )

    with col_reject:
        if st.button('❌ Reject', use_container_width=True, key='btn_reject'):
            _send_decision(
                client,
                HostDecision(action=HostDecisionAction.REJECT),
                'Host: REJECTED elimination',
                'Sent: REJECT',
            )

    with col_override:
        _render_override_col(game_state, client)


def _render_game_control(client: OrchestratorClient) -> None:
    """7.4 — Game control: start new game + event log."""
    st.subheader('🎮 Game Control')
    if st.button(
        '🚀 Start New Game',
        use_container_width=True,
        type='primary',
        key='btn_start',
    ):
        try:
            client.start_game()
            st.session_state['feed'] = []
            st.session_state['event_log'] = ['Game started']
            st.session_state['agent_cache'] = {}
            st.success('New game started!')
        except OrchestratorClientError as exc:
            st.error(str(exc))

    log: list[str] = st.session_state.get('event_log', [])
    if log:
        st.caption('Event log (last 10 entries)')
        for entry in reversed(log[-10:]):
            st.text(f'• {entry}')


def _render_ask_agent(client: OrchestratorClient) -> None:
    """7.5 — Ask agent: form to send a host question to any agent."""
    st.subheader('❓ Ask Agent')
    cache: dict[str, AgentInfo] = st.session_state.get('agent_cache', {})
    if not cache:
        st.info('No agents available. Start a game first.')
        return

    options = [f'{a_id} · {info.persona_name}' for a_id, info in cache.items()]
    selected = st.selectbox('Agent', options, key='ask_agent_sel')
    question = st.text_area(
        'Question',
        placeholder='Are you mafia?',
        key='ask_question',
        height=68,
    )
    if st.button('📨 Ask', key='btn_ask'):
        if selected and question.strip():
            agent_id = selected.split(' ')[0]
            try:
                q_id = client.ask_agent(agent_id, question.strip())
                preview = question.strip()[:40]
                st.session_state['event_log'].append(
                    f'Host → {agent_id}: "{preview}…" (id: {q_id[:8]})'
                )
                st.success('Question sent! Answer will appear in the feed.')
            except OrchestratorClientError as exc:
                st.error(str(exc))


# ── Main fragment (re-runs every 2 s) ─────────────────────────────────


@st.fragment(run_every=2)
def _app() -> None:
    """Entire application rendered as a self-refreshing fragment."""
    client = _get_client()
    _drain_queue()

    game_state = client.get_state()
    agents: dict[str, AgentInfo] = (
        client.get_agents() if game_state and game_state.alive_agents else {}
    )

    st.title('🃏 Mafia-AI — Host Panel')

    col_feed, col_status = st.columns([3, 1])
    with col_status:
        _render_status(game_state, agents)
    with col_feed:
        _render_feed()

    if game_state and game_state.phase == GamePhase.HOST_DECISION:
        _render_host_decision(game_state, client)

    st.divider()
    col_ctrl, col_ask = st.columns(2)
    with col_ctrl:
        _render_game_control(client)
    with col_ask:
        _render_ask_agent(client)


_app()
