import asyncio
import random
import uuid
from collections.abc import AsyncGenerator

from loguru import logger

from config import MafiaServiceSettings
from llm.service import LLM
from shared.database import Database
from shared.models import (
    AgentAnswer,
    AgentInfo,
    AgentRole,
    AgentState,
    AgentStatus,
    GamePhase,
    GameState,
    HostDecision,
    HostDecisionAction,
    Message,
    SystemPrompt,
    VoteEvent,
)

from .agent_logic import AgentLogic
from .event_bus import EventBus, EventType
from .vote_resolver import resolve_votes


class AgentManager:
    """Manages all AI agents in a single process.

    Args:
        llm: LLM service for direct local inference.
        db: Database instance with personas and state storage.

    """

    def __init__(self, llm: LLM, db: Database) -> None:
        self._llm = llm
        self._db = db
        self._agents: dict[str, AgentLogic] = {}

    async def initialize_agent(
        self,
        agent_id: str,
        role: AgentRole,
        persona_id: str,
    ) -> None:
        """Initialize a new agent with given role and persona."""
        persona = await self._db.get_persona(persona_id)

        system_prompt = SystemPrompt(
            persona_id=persona.persona_id,
            name=persona.name,
            persona_type=persona.persona_type,
            prompt=persona.prompt,
        )

        agent_logic = AgentLogic(
            agent_id=agent_id,
            persona=system_prompt,
            llm=self._llm,
            db=self._db,
        )
        self._agents[agent_id] = agent_logic

        state = AgentState(
            agent_id=agent_id,
            role=role,
            persona_id=persona_id,
            message_history=[],
        )
        await self._db.update_agent_state(agent_id, state)

        logger.info(
            f'Agent {agent_id} initialized with role={role}, persona={persona_id}'
        )

    async def get_state(self, agent_id: str) -> AgentState | None:
        """Get current state of an agent from DB."""
        if agent_id not in self._agents:
            return None

        state = await self._db.get_agent_state(agent_id)
        return state

    async def eliminate_agent(self, agent_id: str) -> None:
        """Mark agent as eliminated (remove from active agents)."""
        if agent_id not in self._agents:
            logger.warning(f'Attempted to eliminate non-initialized agent {agent_id}')
            return

        await self._db.update_agent_status(agent_id, AgentStatus.ELIMINATED)
        del self._agents[agent_id]

        logger.info(f'Agent {agent_id} eliminated and removed')

    async def generate_message(self, agent_id: str, phase: str, game_round: int) -> str:
        """Generate a message for the current phase."""
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        agent = self._agents[agent_id]
        phase_enum = GamePhase(phase)
        return await agent.generate_message(phase_enum, game_round)

    async def answer_question(self, agent_id: str, question_text: str) -> str:
        """Generate answer to host question."""
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        agent = self._agents[agent_id]
        return await agent.answer_question(question_text)

    async def close(self) -> None:
        """Cleanup resources (no HTTP client to close)."""
        logger.info('AgentManager closed')


class Game:
    """Unified game orchestrator and agent manager.

    Runs an asyncio game loop as a background task once a game is started.
    Manages all AI agents.

    The FSM cycle per round:
    NIGHT → NIGHT_VOTE → RESOLVE_NIGHT → DAY → DAY_VOTE → HOST_DECISION
    → (next NIGHT | GAME_OVER)

    Args:
        settings: Populated MafiaServiceSettings instance.
        llm: LLM service for direct local inference.
        event_bus: event bus for UI notifications.
        dbL Databse.

    """

    # Game state
    _round: int
    _phase: GamePhase
    _alive: list[str]
    _eliminated: list[str]
    _roles: dict[str, AgentRole]

    # Message history and SSE subscribers
    _messages: list[Message]
    _message_queues: list[asyncio.Queue[Message]]

    # Vote collection (single queue for vote.* routing key)
    _vote_queue: asyncio.Queue[VoteEvent]

    # Host decision synchronisation
    _host_decision: HostDecision | None
    _host_decision_event: asyncio.Event

    # Background game task
    _game_task: asyncio.Task | None
    _game_active: bool

    def __init__(
        self,
        settings: MafiaServiceSettings,
        llm: LLM,
        event_bus: EventBus,
        db: Database,
    ) -> None:
        self._settings = settings
        self._db = db
        self._llm = llm
        self._agent_manager = AgentManager(llm, db)
        self._event_bus = event_bus
        self.default_game_stats()

    async def start(self) -> None:
        """Connect to Database and initialize game data."""
        try:
            await self.stop()
            await self._llm.start()
            await self._db.connect()
            await self._db.init_from_yaml(self._settings.db_yaml_path)
            logger.info('Game started')
        except Exception as exc:
            logger.error(f'Game failed to start: {exc.__str__()}')
            raise

    async def stop(self) -> None:
        """Cancel the game task and close all connections."""
        if self._game_task is not None and not self._game_task.done():
            self._game_task.cancel()
        await self._agent_manager.close()
        await self._db.close()
        await self._llm.stop()
        self.default_game_stats()
        logger.info('Game stopped')

    def default_game_stats(self) -> None:
        """Set default game stats"""
        self._round = 0
        self._phase = GamePhase.DAY
        self._alive = []
        self._eliminated = []
        self._roles = {}
        self._messages = []
        self._message_queues = []
        self._vote_queue = asyncio.Queue()
        self._host_decision = None
        self._host_decision_event = asyncio.Event()
        self._game_task = None
        self._game_active = False

    async def begin_game(self) -> None:
        """Initialise roles/personas and launch the game loop.

        Raises:
            RuntimeError: If a game is already in progress.

        """
        if self._game_active:
            raise RuntimeError('A game is already in progress. ')
        await self._init_game()
        self._game_task = asyncio.create_task(self._run_game_loop())

    def get_game_state(self) -> GameState:
        """Return a snapshot of the current game state."""
        return GameState(
            round=self._round,
            phase=self._phase,
            alive_agents=self._alive,
            eliminated=self._eliminated,
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
        """Get info for all alive agents concurrently.

        Returns:
            Mapping of agent_id to AgentInfo with display fields.

        """
        tasks = {
            agent_id: self._agent_manager.get_state(agent_id)
            for agent_id in self._alive
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        infos = {}
        for agent_id, result in zip(tasks.keys(), results):
            if isinstance(result, AgentState):
                persona_name = 'Unknown'
                if result.persona_id:
                    try:
                        persona = await self._db.get_persona(result.persona_id)
                        persona_name = persona.name
                    except Exception:
                        pass

                status = (
                    AgentStatus.ALIVE
                    if agent_id in self._alive
                    else AgentStatus.ELIMINATED
                )
                infos[agent_id] = AgentInfo(
                    agent_id=agent_id,
                    persona_name=persona_name,
                    role=result.role,
                    status=status,
                    container_id=None,
                )
        return infos

    async def get_agent_info(self, agent_id: str) -> AgentInfo | None:
        """Get info for a single agent.

        Args:
            agent_id: ID of the agent to query.

        Returns:
            AgentInfo on success, or None if unreachable / unknown.

        """
        state = await self._agent_manager.get_state(agent_id)
        if state is None:
            return None

        persona_name = 'Unknown'
        if state.persona_id:
            try:
                persona = await self._db.get_persona(state.persona_id)
                persona_name = persona.name
            except Exception:
                pass

        status = (
            AgentStatus.ALIVE if agent_id in self._alive else AgentStatus.ELIMINATED
        )
        return AgentInfo(
            agent_id=agent_id,
            persona_name=persona_name,
            role=state.role,
            status=status,
            container_id=None,
        )

    async def ask_agent(
        self,
        agent_id: str,
        question_text: str,
        timeout: float = 60.0,
    ) -> str:
        """Ask agent a question and return the answer.

        Args:
            agent_id: ID of the agent to ask.
            question_text: Question text from the host.
            timeout: Maximum seconds to wait for answer.

        Returns:
            Answer text.

        """
        try:
            answer_text = await asyncio.wait_for(
                self._agent_manager.answer_question(agent_id, question_text),
                timeout=timeout,
            )

            # Create AgentAnswer event for UI
            answer = AgentAnswer(
                question_id=str(uuid.uuid4()),
                agent_id=agent_id,
                answer_text=answer_text,
            )

            # Publish to EventBus for UI
            await self._event_bus.publish_async(EventType.ANSWER, answer)

            return answer_text
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(f'Failed to get answer from {agent_id}: {exc.__str__()}')
            raise

    async def force_stop_agent(self, agent_id: str) -> None:
        """Force-eliminate an agent.

        Args:
            agent_id: ID of the agent to remove from the game.

        """
        await self._eliminate_agent(agent_id)

    async def _init_game(self) -> None:
        """Assign roles and personas, reset state, publish init messages."""
        all_agent_ids = [f'agent-{n}' for n in range(1, self._settings.agent_count + 1)]

        # Assign roles — randomly pick mafia agents
        mafia_set = set(random.sample(all_agent_ids, self._settings.mafia_count))
        self._roles = {
            aid: (AgentRole.MAFIA if aid in mafia_set else AgentRole.CITIZEN)
            for aid in all_agent_ids
        }

        # Assign personas from Database (unique when possible)
        personas = await self._db.get_personas()
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
        self._drain_vote_queue()

        # Initialize agents via agent manager (direct call, no HTTP)
        for aid in all_agent_ids:
            await self._agent_manager.initialize_agent(
                aid, self._roles[aid], persona_map[aid]
            )
            logger.info(
                f'Initialized {aid} with role {self._roles[aid]} '
                f'(persona {persona_map[aid]})'
            )

        logger.info(
            f'Game initialised: {self._settings.agent_count} agents, '
            f'{self._settings.mafia_count} mafia'
        )

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
        """Request agents to generate messages during NIGHT or DAY speaking phase.

        Each agent gets a time slice; if generation fails within the slice the
        orchestrator moves on (timeout not fatal).

        Args:
            mafia_only: When True only mafia agents generate messages.

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

            try:
                message_text = await asyncio.wait_for(
                    self._agent_manager.generate_message(
                        agent_id, self._phase.value, self._round
                    ),
                    timeout=per_agent_timeout,
                )

                # Store message in history
                message = Message(
                    sender_id=agent_id,
                    agent_id=agent_id,
                    round=self._round,
                    phase=self._phase,
                    content=message_text,
                )
                self._messages.append(message)

                # Publish to EventBus for UI
                await self._event_bus.publish_async(EventType.MESSAGE, message)

                # Notify SSE subscribers
                for queue in self._message_queues:
                    await queue.put(message)

                logger.info(
                    f'Agent {agent_id} spoke in {self._phase} round {self._round}'
                )

            except asyncio.TimeoutError:
                logger.warning(
                    f'Agent {agent_id} did not respond within '
                    f'{per_agent_timeout:.1f}s; moving on'
                )
            except Exception as exc:
                logger.error(f'Agent {agent_id} message generation failed: {exc}')

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
        """Remove agent from alive list, publish state, and eliminate via manager.

        Args:
            agent_id: ID of the agent to eliminate.

        """
        if agent_id not in self._alive:
            return

        self._alive.remove(agent_id)
        self._eliminated.append(agent_id)

        await self._agent_manager.eliminate_agent(agent_id)
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
        """Publish the current GameState to EventBus for UI."""
        state = GameState(
            round=self._round,
            phase=self._phase,
            alive_agents=list(self._alive),
            eliminated=list(self._eliminated),
        )
        # Publish to EventBus for UI
        await self._event_bus.publish_async(EventType.STATE_CHANGE, state)

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
