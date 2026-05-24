import asyncio
import json
import random
from collections.abc import AsyncGenerator

from loguru import logger

from shared.messaging import MessagingClient
from shared.models import (
    AgentInfo,
    AgentInit,
    AgentRole,
    GamePhase,
    GameState,
    HostDecision,
    HostDecisionAction,
    HostQuestion,
    Message,
    TurnSignal,
    VoteEvent,
)
from shared.vectordb_client import VectorDBClient

from ..config import OrchestratorSettings
from .agent_poller import AgentEndpoint, AgentPoller
from .vote_resolver import resolve_votes


class OrchestratorService:
    """Game orchestrator: manages phases, agents, votes, and host interaction.

    Runs an asyncio game loop as a background task once a game is started.
    Coordinates agent messaging via RabbitMQ and exposes state to the FastAPI
    REST layer.

    The FSM cycle per round:
    NIGHT → NIGHT_VOTE → RESOLVE_NIGHT → DAY → DAY_VOTE → HOST_DECISION
    → (next NIGHT | GAME_OVER)

    Args:
        settings: Populated OrchestratorSettings instance.

    """

    def __init__(self, settings: OrchestratorSettings) -> None:
        self._settings = settings
        self._messaging = MessagingClient(settings.amqp_url)
        self._vectordb = VectorDBClient(settings.vectordb_host, settings.vectordb_port)
        self._poller = AgentPoller(self._build_endpoints(), settings.docker_socket_url)

        # Game state
        self._round: int = 0
        self._phase: GamePhase = GamePhase.DAY
        self._alive: list[str] = []
        self._eliminated: list[str] = []
        self._roles: dict[str, AgentRole] = {}

        # Message history and SSE subscribers
        self._messages: list[Message] = []
        self._message_queues: list[asyncio.Queue[Message]] = []

        # Vote collection (single queue for vote.* routing key)
        self._vote_queue: asyncio.Queue[VoteEvent] = asyncio.Queue()

        # Host decision synchronisation
        self._host_decision: HostDecision | None = None
        self._host_decision_event: asyncio.Event = asyncio.Event()

        # Agent answer futures keyed by question_id
        self._pending_answers: dict[str, asyncio.Future[str]] = {}
        self._answer_cache: dict[str, str] = {}

        # Per-agent turn completion events
        self._turn_events: dict[str, asyncio.Event] = {}

        # Background game task
        self._game_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._game_active: bool = False

    # ------------------------------------------------------------------
    # Startup / shutdown
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to RabbitMQ and subscribe to all game channels."""
        await self._messaging.connect()
        await self._messaging.subscribe('message.*', self._on_message)
        await self._messaging.subscribe('vote.*', self._on_vote)
        await self._messaging.subscribe('host.answer.*', self._on_host_answer)
        logger.info('OrchestratorService started')

    async def stop(self) -> None:
        """Cancel the game task and close all connections."""
        if self._game_task is not None and not self._game_task.done():
            self._game_task.cancel()
        await self._messaging.close()
        await self._poller.close()
        logger.info('OrchestratorService stopped')

    # ------------------------------------------------------------------
    # Public interface (called by REST handlers)
    # ------------------------------------------------------------------

    async def begin_game(self) -> None:
        """Initialise roles/personas and launch the game loop.

        Raises:
            RuntimeError: If a game is already in progress.

        """
        if self._game_active:
            raise RuntimeError('A game is already in progress')
        await self._init_game()
        self._game_task = asyncio.create_task(self._run_game_loop())

    def get_game_state(self) -> GameState:
        """Return a snapshot of the current game state."""
        return GameState(
            round=self._round,
            phase=self._phase,
            alive_agents=list(self._alive),
            eliminated=list(self._eliminated),
        )

    def submit_host_decision(self, decision: HostDecision) -> None:
        """Accept a host decision and unblock the waiting game loop.

        Args:
            decision: The host's action and optional override target.

        """
        self._host_decision = decision
        self._host_decision_event.set()

    async def subscribe_messages(self) -> AsyncGenerator[Message, None]:
        """Yield game messages for SSE streaming.

        Replays the full history first, then streams arriving messages.

        Yields:
            Message objects in chronological order.

        """
        queue: asyncio.Queue[Message] = asyncio.Queue()
        self._message_queues.append(queue)
        try:
            for msg in list(self._messages):
                yield msg
            while True:
                msg = await queue.get()
                yield msg
        finally:
            self._message_queues.remove(queue)

    async def get_agents_info(self) -> dict[str, AgentInfo]:
        """Poll all alive agents concurrently and return their info.

        Returns:
            Mapping of agent_id to AgentInfo.

        """
        return await self._poller.poll_all(self._alive)

    async def get_agent_info(self, agent_id: str) -> AgentInfo | None:
        """Poll a single agent and return its info.

        Args:
            agent_id: ID of the agent to poll.

        Returns:
            AgentInfo on success, or None if unreachable / unknown.

        """
        return await self._poller.poll_agent(agent_id)

    async def ask_agent(
        self, agent_id: str, question_id: str, question_text: str
    ) -> None:
        """Publish a HostQuestion to the target agent via RabbitMQ.

        Args:
            agent_id: ID of the agent to ask.
            question_id: Unique UUID for this question.
            question_text: Question text from the host.

        """
        question = HostQuestion(
            question_id=question_id,
            target_agent_id=agent_id,
            question_text=question_text,
        )
        await self._messaging.publish(f'host.question.{agent_id}', question)

    async def get_agent_answer(
        self, question_id: str, timeout: float = 60.0
    ) -> str | None:
        """Wait for an agent's answer to a previously asked question.

        Checks the answer cache first; if not yet received, blocks until the
        answer arrives or the timeout expires.

        Args:
            question_id: UUID of the question to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            Answer text, or None if timed out.

        """
        cached = self._answer_cache.pop(question_id, None)
        if cached is not None:
            return cached

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        self._pending_answers[question_id] = fut
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_answers.pop(question_id, None)

    async def force_stop_agent(self, agent_id: str) -> None:
        """Force-eliminate an agent and stop its container.

        Args:
            agent_id: ID of the agent to remove from the game.

        """
        await self._eliminate_agent(agent_id)

    # ------------------------------------------------------------------
    # Game initialisation
    # ------------------------------------------------------------------

    async def _init_game(self) -> None:
        """Assign roles and personas, reset state, publish init messages."""
        all_agent_ids = [f'agent-{n}' for n in range(1, self._settings.agent_count + 1)]

        # Assign roles — randomly pick mafia agents
        mafia_set = set(random.sample(all_agent_ids, self._settings.mafia_count))
        self._roles = {
            aid: (AgentRole.MAFIA if aid in mafia_set else AgentRole.CITIZEN)
            for aid in all_agent_ids
        }

        # Assign personas from VectorDB (unique when possible)
        personas = self._vectordb.list_personas()
        if len(personas) >= self._settings.agent_count:
            sampled = random.sample(personas, self._settings.agent_count)
        else:
            sampled = random.choices(personas, k=self._settings.agent_count)

        persona_map = {
            aid: sampled[i].persona_id for i, aid in enumerate(all_agent_ids)
        }

        # Reset all game state
        self._round = 1
        self._alive = list(all_agent_ids)
        self._eliminated = []
        self._messages = []
        self._game_active = True
        self._host_decision = None
        self._host_decision_event.clear()
        self._answer_cache.clear()
        self._drain_vote_queue()

        # Publish personalised role assignment to each agent
        for aid in all_agent_ids:
            init_msg = AgentInit(agent_id=aid, role=self._roles[aid])
            await self._messaging.publish(f'game.init.{aid}', init_msg)
            logger.info(
                f'Assigned role {self._roles[aid]} to {aid} '
                f'(persona {persona_map[aid]})'
            )

        logger.info(
            f'Game initialised: {self._settings.agent_count} agents, '
            f'{self._settings.mafia_count} mafia'
        )

    # ------------------------------------------------------------------
    # Game FSM loop
    # ------------------------------------------------------------------

    async def _run_game_loop(self) -> None:
        """Main finite-state-machine game loop."""
        try:
            while self._game_active:
                # --- NIGHT ---
                await self._transition_phase(GamePhase.NIGHT)
                await self._run_speak_phase(mafia_only=True)

                # --- NIGHT_VOTE ---
                await self._transition_phase(GamePhase.NIGHT_VOTE)
                night_votes = await self._collect_votes(
                    len(self._mafia_alive()), 'night'
                )

                # --- RESOLVE_NIGHT ---
                await self._transition_phase(GamePhase.RESOLVE_NIGHT)
                eliminated_id = resolve_votes(night_votes)
                if eliminated_id:
                    await self._eliminate_agent(eliminated_id)
                await self._publish_game_state()

                if self._check_and_handle_win():
                    break

                # --- DAY ---
                await self._transition_phase(GamePhase.DAY)
                await self._run_speak_phase(mafia_only=False)

                # --- DAY_VOTE ---
                await self._transition_phase(GamePhase.DAY_VOTE)
                day_votes = await self._collect_votes(len(self._alive), 'day')

                # --- HOST_DECISION ---
                await self._transition_phase(GamePhase.HOST_DECISION)
                eliminated_id = await self._wait_for_host_decision(day_votes)
                if eliminated_id:
                    await self._eliminate_agent(eliminated_id)
                await self._publish_game_state()

                if self._check_and_handle_win():
                    break

                self._round += 1

        except asyncio.CancelledError:
            logger.info('Game loop cancelled')
        finally:
            self._game_active = False
            logger.info('Game loop ended')

    async def _run_speak_phase(self, mafia_only: bool) -> None:
        """Send turn signals sequentially during NIGHT or DAY speaking phase.

        Each agent gets a time slice; if no message arrives within the slice the
        orchestrator moves on (timeout not fatal).

        Args:
            mafia_only: When True only mafia agents receive a turn signal.

        """
        targets = self._mafia_alive() if mafia_only else list(self._alive)
        if not targets:
            return

        per_agent_timeout = max(
            self._settings.phase_duration_seconds / len(targets), 5.0
        )

        for agent_id in targets:
            if agent_id not in self._alive:
                continue

            event = asyncio.Event()
            self._turn_events[agent_id] = event

            signal = TurnSignal(
                agent_id=agent_id,
                phase=self._phase,
                round=self._round,
            )
            await self._messaging.publish(f'game.turn.{agent_id}', signal)

            try:
                await asyncio.wait_for(event.wait(), timeout=per_agent_timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f'Agent {agent_id} did not respond within '
                    f'{per_agent_timeout:.1f}s; moving on'
                )
            finally:
                self._turn_events.pop(agent_id, None)

    async def _collect_votes(self, expected: int, suffix: str) -> list[VoteEvent]:
        """Collect votes from the queue until expected count or timeout.

        Stale votes (wrong round) are silently discarded. The phase transition
        that precedes this call ensures agents start voting for the current round.

        Args:
            expected: Number of votes to wait for.
            suffix: ``'night'`` or ``'day'`` for log messages.

        Returns:
            List of collected VoteEvents for the current round.

        """
        self._drain_vote_queue()
        votes: list[VoteEvent] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.vote_timeout_seconds

        while len(votes) < expected:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                vote = await asyncio.wait_for(self._vote_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if vote.round != self._round:
                logger.debug(
                    f'Discarding stale vote from round {vote.round} '
                    f'(current round {self._round})'
                )
                continue
            votes.append(vote)

        logger.info(f'Collected {len(votes)}/{expected} {suffix} votes')
        return votes

    async def _wait_for_host_decision(self, votes: list[VoteEvent]) -> str | None:
        """Block until the host submits a decision, then resolve the elimination.

        Args:
            votes: Day votes for majority resolution (used for APPROVE action).

        Returns:
            agent_id to eliminate, or None if no elimination.

        Raises:
            ValueError: If an unknown decision action is received.

        """
        self._host_decision_event.clear()
        self._host_decision = None
        await self._host_decision_event.wait()

        decision = self._host_decision
        if decision is None:
            return None

        if decision.action == HostDecisionAction.APPROVE:
            return resolve_votes(votes)
        if decision.action == HostDecisionAction.REJECT:
            return None
        if decision.action == HostDecisionAction.OVERRIDE:
            return decision.target_id
        raise ValueError(f'Unknown decision action: {decision.action}')

    async def _eliminate_agent(self, agent_id: str) -> None:
        """Remove agent from alive list, publish state, and stop its container.

        Args:
            agent_id: ID of the agent to eliminate.

        """
        if agent_id not in self._alive:
            return

        self._alive.remove(agent_id)
        self._eliminated.append(agent_id)

        elimination_state = GameState(
            round=self._round,
            phase=self._phase,
            alive_agents=list(self._alive),
            eliminated=list(self._eliminated),
        )
        await self._messaging.publish(
            f'game.state.eliminated.{agent_id}', elimination_state
        )
        await self._poller.stop_container(agent_id)
        logger.info(f'Agent {agent_id} eliminated')

    def _check_and_handle_win(self) -> bool:
        """Check win conditions and set GAME_OVER phase if the game has ended.

        Returns:
            True if the game is over, False if it should continue.

        """
        mafia_alive = self._mafia_alive()
        citizen_alive = [
            a for a in self._alive if self._roles.get(a) == AgentRole.CITIZEN
        ]

        if not mafia_alive:
            logger.info('Citizens win: all mafia agents eliminated')
            self._phase = GamePhase.GAME_OVER
            self._game_active = False
            return True

        if len(citizen_alive) <= len(mafia_alive):
            logger.info('Mafia wins: citizens are outnumbered')
            self._phase = GamePhase.GAME_OVER
            self._game_active = False
            return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mafia_alive(self) -> list[str]:
        return [a for a in self._alive if self._roles.get(a) == AgentRole.MAFIA]

    async def _transition_phase(self, phase: GamePhase) -> None:
        """Update the phase and broadcast the new game state.

        Args:
            phase: Target phase to transition into.

        """
        self._phase = phase
        await self._publish_game_state()
        logger.info(f'Phase -> {phase} (round {self._round})')

    async def _publish_game_state(self) -> None:
        """Publish the current GameState to the ``game.state`` routing key."""
        state = GameState(
            round=self._round,
            phase=self._phase,
            alive_agents=list(self._alive),
            eliminated=list(self._eliminated),
        )
        await self._messaging.publish('game.state', state)

    def _build_endpoints(self) -> list[AgentEndpoint]:
        """Build the AgentEndpoint list from settings."""
        endpoints = []
        for n in range(1, self._settings.agent_count + 1):
            agent_id = f'agent-{n}'
            host = self._settings.agent_host_pattern.format(n=n)
            endpoints.append(
                AgentEndpoint(
                    agent_id=agent_id,
                    host=host,
                    port=self._settings.agent_http_port,
                    container_name=host,
                )
            )
        return endpoints

    def _drain_vote_queue(self) -> None:
        """Discard any votes left in the queue from previous phases."""
        drained = 0
        while not self._vote_queue.empty():
            try:
                self._vote_queue.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logger.debug(f'Drained {drained} stale votes from queue')

    # ------------------------------------------------------------------
    # RabbitMQ callbacks
    # ------------------------------------------------------------------

    async def _on_message(self, routing_key: str, body: bytes) -> None:
        """Store game messages, notify SSE subscribers and signal turn complete."""
        try:
            msg = Message.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(f'Failed to parse message ({routing_key}): {exc}')
            return

        self._messages.append(msg)
        for queue in self._message_queues:
            queue.put_nowait(msg)
        self._signal_turn_complete(msg.sender_id)

    async def _on_vote(self, routing_key: str, body: bytes) -> None:
        """Enqueue incoming VoteEvent for collection by the active phase."""
        try:
            vote = VoteEvent.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(f'Failed to parse vote ({routing_key}): {exc}')
            return

        await self._vote_queue.put(vote)
        logger.debug(f'Vote queued: {vote.voter_id} -> {vote.target_id}')

    async def _on_host_answer(self, routing_key: str, body: bytes) -> None:
        """Route agent answers to waiting REST futures or cache them."""
        try:
            from shared.models import AgentAnswer

            answer = AgentAnswer.model_validate(json.loads(body))
        except Exception as exc:
            logger.error(f'Failed to parse host.answer ({routing_key}): {exc}')
            return

        fut = self._pending_answers.get(answer.question_id)
        if fut is not None and not fut.done():
            fut.set_result(answer.answer_text)
        else:
            # No one is waiting yet — cache so the polling endpoint can retrieve it
            self._answer_cache[answer.question_id] = answer.answer_text

    def _signal_turn_complete(self, agent_id: str) -> None:
        """Mark the agent's turn as done so the game loop can advance."""
        event = self._turn_events.get(agent_id)
        if event is not None:
            event.set()
