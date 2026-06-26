import asyncio
import random
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from loguru import logger

from config import MafiaServiceSettings
from llm.service import LLM
from shared.database import Database
from shared.exceptions import EmptySharingException
from shared.models import (
    Agent,
    AgentAnswer,
    AgentRole,
    AgentStateIn,
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

    def __init__(self, llm: LLM, db: Database, game_id: int) -> None:
        self.llm = llm
        self.db = db
        self._agents: dict[int, AgentLogic] = {}
        self.game_id = game_id

    async def initialize_agent(
        self,
        state: AgentStateIn,
        persona: SystemPrompt,
    ) -> int:
        """Initialize a new agent.

        TODO: test me

        """
        agent_id = await self.db.init_agent(state=state, game_id=self.game_id)
        self._agents[agent_id] = AgentLogic(
            agent_id=agent_id,
            persona=persona,
            llm=self.llm,
            db=self.db,
        )
        logger.info(
            f'Agent {agent_id} initialized with '
            f'role={state.role.value}, persona={persona.persona_id}'
        )
        return agent_id

    async def eliminate_agent(self, agent_id: int) -> None:
        """Mark agent as eliminated (remove from active agents)."""
        if agent_id not in self._agents:
            logger.warning(f'Attempted to eliminate non-initialized agent {agent_id}')
            return

        await self.db.update_agent_status(agent_id, AgentStatus.ELIMINATED)
        del self._agents[agent_id]

        logger.info(f'Agent {agent_id} eliminated and removed')

    async def generate_message(self, agent_id: int, phase: str, game_round: int) -> str:
        """Generate a message for the current phase."""
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        agent = self._agents[agent_id]
        phase_enum = GamePhase(phase)
        return await agent.generate_message(phase_enum, game_round)

    async def answer_question(self, agent_id: int, question_text: str) -> str:
        """Generate answer to host question."""
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        agent = self._agents[agent_id]
        return await agent.answer_question(question_text)


@dataclass
class Shared:
    """Cached and shared data of game"""

    # Game state
    all_personas: dict[int, SystemPrompt]
    game_id: int
    system_agent_id: int
    mafia_agents_ids: list[int]
    cityzen_agents_ids: list[int]
    agent_manager: AgentManager

    # Message history and SSE subscribers
    messages: list[Message]
    message_queues: list[asyncio.Queue[Message]]

    # Vote collection
    vote_queue: asyncio.Queue[VoteEvent]

    # Host decision synchronisation
    host_decision: HostDecision
    host_decision_event: asyncio.Event
    game_task: asyncio.Task

    game_active: bool


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

    def __init__(
        self,
        settings: MafiaServiceSettings,
        llm: LLM,
        event_bus: EventBus,
        db: Database,
    ) -> None:
        self._settings = settings
        self.db = db
        self.llm = llm
        self.event_bus = event_bus
        self._shared: Shared | None = None

    @property
    def shared(self) -> Shared:
        if not self._shared:
            raise EmptySharingException('Game is not started.')
        return self._shared

    @shared.setter
    def shared(self, shared: Shared) -> None:
        if self._shared and not self._shared.game_task.done():
            self._shared.game_task.cancel()
        self._shared = shared

    @shared.deleter
    def shared(self) -> None:
        if self._shared and not self._shared.game_task.done():
            self._shared.game_task.cancel()
        self._shared = None

    async def start(self) -> None:
        """Asyncronously start all services before begin game

        TODO: test me

        """
        try:
            await self.stop()
            await self.llm.start()
            await self.db.connect()
            # CHECK: init personas once at the db connect
            await self.db.init_personas_from_yaml(self._settings.db_yaml_path)
            logger.info('Game engine started')
        except Exception as exc:
            logger.error(f'Game engine failed to start: {exc.__str__()}')
            raise

    async def stop(self) -> None:
        """Stop all game services

        TODO: test me

        """
        await self.end_game()
        await self.db.close()
        await self.llm.stop()
        logger.info('Game engine stopped')

    async def begin_game(self) -> None:
        """Initialise roles/personas and launch the game loop.

        Raises:
            RuntimeError: If a game is already in progress.

        TODO: test me

        """
        try:
            if self.shared.game_active:
                raise RuntimeError('A game is already in progress. ')
            else:
                del self.shared
        except EmptySharingException:
            ...

        all_personas = {p.persona_id: p for p in await self.db.get_personas()}
        game_id = await self.db.init_game()

        agent_manager = AgentManager(
            llm=self.llm,
            db=self.db,
            game_id=game_id,
        )

        # roles
        system, mafia, cityzen = self.split_personas()

        # Initialize agents via agent manager
        # NOTE: is blocked calls, but no matter
        system_agent_id = await agent_manager.initialize_agent(
            state=AgentStateIn(
                role=AgentRole.SYSTEM,
                status=AgentStatus.ALIVE,
                persona_id=system,
            ),
            persona=all_personas[system],
        )
        mafia_agents_ids = []
        for m in mafia:
            mafia_agents_ids.append(
                await agent_manager.initialize_agent(
                    state=AgentStateIn(
                        role=AgentRole.MAFIA,
                        status=AgentStatus.ALIVE,
                        persona_id=m,
                    ),
                    persona=all_personas[m],
                )
            )
        cityzen_agents_ids = []
        for c in cityzen:
            cityzen_agents_ids.append(
                await agent_manager.initialize_agent(
                    state=AgentStateIn(
                        role=AgentRole.CITIZEN,
                        status=AgentStatus.ALIVE,
                        persona_id=c,
                    ),
                    persona=all_personas[c],
                )
            )

        self.shared = Shared(
            all_personas=all_personas,
            game_id=game_id,
            system_agent_id=system_agent_id,
            mafia_agents_ids=mafia_agents_ids,
            cityzen_agents_ids=cityzen_agents_ids,
            agent_manager=agent_manager,
            messages=[],
            message_queues=[],
            vote_queue=asyncio.Queue(),
            host_decision=HostDecision(),
            host_decision_event=asyncio.Event(),
            game_task=asyncio.create_task(self._run_game_loop()),
            game_active=True,
        )
        logger.info('Game begin.')

    async def end_game(self) -> None:
        del self.shared
        logger.info('Game end.')

    def submit_host_decision(self, decision: HostDecision) -> None:
        """Accept a host decision and unblock the waiting game loop.

        Args:
            decision: The host's action and optional override target.

        """
        self.shared.host_decision = decision
        self.shared.host_decision_event.set()

    async def subscribe_messages(self) -> AsyncGenerator[Message, None]:
        """Yield game messages for SSE streaming.

        Replays the full history first, then streams arriving messages.

        Yields:
            Message objects in chronological order.

        FIXME: what is it?

        """
        queue: asyncio.Queue[Message] = asyncio.Queue()
        self.shared.message_queues.append(queue)
        try:
            for msg in list(self.shared.messages):
                yield msg
            while True:
                msg = await queue.get()
                yield msg
        finally:
            self.shared.message_queues.remove(queue)

    async def get_alive_agents(self) -> dict[int, Agent]:
        """Get info for all alive agents.

        Returns:
            dict[int, Agent]: Mapping of alive agent_id to Agent.

        TODO: test me

        """
        states = await self.db.get_agents_state(
            game_id=self.shared.game_id,
            status=AgentStatus.ALIVE,
        )

        return {
            state.agent_id: Agent(
                state=state,
                persona=self.shared.all_personas[state.persona_id],
            )
            for state in states
        }

    async def get_agent(self, agent_id: int) -> Agent:
        """Get info for a single agent.

        Args:
            agent_id: ID of the agent to query.

        Returns:
            Agent.

        TODO: test me

        """
        state = await self.db.get_agent_state(agent_id=agent_id)
        return Agent(
            state=state,
            persona=self.shared.all_personas[state.persona_id],
        )

    async def ask_agent(
        self,
        agent_id: int,
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
                self.shared.agent_manager.answer_question(agent_id, question_text),
                timeout=timeout,
            )

            # Create AgentAnswer event for UI
            answer = AgentAnswer(
                question_id=str(uuid.uuid4()),
                agent_id=agent_id,
                answer_text=answer_text,
            )

            # Publish to EventBus for UI
            await self.event_bus.publish_async(EventType.ANSWER, answer)

            return answer_text
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(f'Failed to get answer from {agent_id}: {exc.__str__()}')
            raise

    async def force_stop_agent(self, agent_id: int) -> None:
        """Force-eliminate an agent.

        Args:
            agent_id: ID of the agent to remove from the game.

        """
        await self._eliminate_agent(agent_id)

    def split_personas(self) -> tuple[int, list[int], list[int]]:
        """Split personas.

        Returns:
            tuple[int, list[int], list[int]]: system, mafia, cityzen

        TODO: test me

        """
        system = list(self.shared.all_personas.keys())[0]
        remaining = list(self.shared.all_personas.keys())[1:]
        mafia = random.sample(remaining, 3)
        cityzen = [p for p in remaining if p != system and p not in mafia]
        return (system, mafia, cityzen)

    async def _run_game_loop(self) -> None:
        """Main finite-state-machine game loop.

        TODO: test me, concurent
        """
        try:
            while self.shared.game_active:
                mafia = await self.db.get_mafia_ids(
                    game_id=self.shared.game_id,
                    status=AgentStatus.ALIVE,
                )
                # --- NIGHT ---
                game_state = await self._transition_phase(phase=GamePhase.NIGHT)
                await self._run_speak_phase(mafia_only=True, game_state=game_state)

                # --- NIGHT_VOTE ---
                await self._transition_phase(phase=GamePhase.NIGHT_VOTE)
                night_votes = await self._collect_votes(
                    expected=len(mafia),
                    suffix='night',
                )

                # --- RESOLVE_NIGHT ---
                game_state = await self._transition_phase(phase=GamePhase.RESOLVE_NIGHT)
                eliminated_id = resolve_votes(votes=night_votes)
                if eliminated_id:
                    await self._eliminate_agent(agent_id=eliminated_id)
                if self._check_and_handle_win():
                    break

                # --- DAY ---
                game_state = await self._transition_phase(phase=GamePhase.DAY)
                await self._run_speak_phase(mafia_only=False, game_state=game_state)

                # --- DAY_VOTE ---
                await self._transition_phase(phase=GamePhase.DAY_VOTE)
                alive = await self.db.get_agents_ids(
                    game_id=self.shared.game_id,
                    status=AgentStatus.ALIVE,
                )
                day_votes = await self._collect_votes(expected=len(alive), suffix='day')

                # --- HOST_DECISION ---
                game_state = await self._transition_phase(phase=GamePhase.HOST_DECISION)
                eliminated_id = await self._wait_for_host_decision(votes=day_votes)
                if eliminated_id:
                    await self._eliminate_agent(agent_id=eliminated_id)
                if self._check_and_handle_win():
                    break

                await self.db.update_round(
                    game_id=self.shared.game_id,
                    round=game_state.round + 1,
                )
        except asyncio.CancelledError:
            logger.info('Game loop cancelled')
        finally:
            self._game_active = False
            logger.info('Game loop ended')

    async def _transition_phase(self, phase: GamePhase) -> GameState:
        """Update the phase and broadcast the new game state.

        Args:
            phase (GamePhase): target phase to transition into.

        Returns:
            GameState

        TODO: test me

        """
        await self.db.update_game_phase(game_id=self.shared.game_id, phase=phase)
        logger.info(f'Phase -> {phase}')
        game_state = await self.db.get_game_state(game_id=self.shared.game_id)
        await self.event_bus.publish_async(EventType.STATE_CHANGE, game_state)
        return game_state

    async def _eliminate_agent(self, agent_id: int) -> None:
        """Remove agent from alive list, publish state, and eliminate via manager.

        Args:
            agent_id: ID of the agent to eliminate.

        """
        alive = await self.db.get_agents_ids(
            game_id=self.shared.game_id,
            status=AgentStatus.ALIVE,
        )
        if agent_id not in alive:
            return

        await self.shared.agent_manager.eliminate_agent(agent_id)
        logger.info(f'Agent {agent_id} eliminated')
        game_state = await self.db.get_game_state(game_id=self.shared.game_id)
        await self.event_bus.publish_async(EventType.STATE_CHANGE, game_state)

    async def _run_speak_phase(self, mafia_only: bool, game_state: GameState) -> None:
        """Request agents to generate messages during NIGHT or DAY speaking phase.

        Args:
            mafia_only: When True only mafia agents generate messages.
            game_state (GameState): game state.

        TODO: test me, concurent

        """
        if mafia_only:
            targets = await self.db.get_mafia_ids(
                game_id=self.shared.game_id,
                status=AgentStatus.ALIVE,
            )
        else:
            targets = await self.db.get_agents_ids(
                game_id=self.shared.game_id,
                status=AgentStatus.ALIVE,
            )
        if not targets:
            return

        per_agent_timeout = max(
            self._settings.phase_duration_seconds / len(targets),
            5.0,
        )

        # FIXME: not async for - use tasks and gather or tasksgroup
        for agent_id in targets:
            try:
                message_text = await asyncio.wait_for(
                    self.shared.agent_manager.generate_message(
                        agent_id,
                        game_state.phase.value,
                        game_state.round,
                    ),
                    timeout=per_agent_timeout,
                )

                # Store message in history
                message = Message(
                    sender_id=agent_id,
                    agent_id=agent_id,
                    round=game_state.round,
                    phase=game_state.phase,
                    content=message_text,
                )
                self.shared.messages.append(message)

                # Publish to EventBus for UI
                await self.event_bus.publish_async(EventType.MESSAGE, message)

                # Notify SSE subscribers
                for queue in self.shared.message_queues:
                    await queue.put(message)

                logger.info(
                    f'Agent {agent_id} spoke in {game_state.phase}'
                    f'round {game_state.round}'
                )

            except asyncio.TimeoutError:
                logger.warning(
                    f'Agent {agent_id} did not respond within '
                    f'{per_agent_timeout:.1f}s; moving on'
                )
            except Exception as exc:
                logger.error(
                    f'Agent {agent_id} message generation failed: {exc.__str__()}'
                )

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
                vote = await asyncio.wait_for(
                    self.shared.vote_queue.get(), timeout=remaining
                )
            except asyncio.TimeoutError:
                break
            game_state = await self.db.get_game_state(game_id=self.shared.game_id)
            if vote.round != game_state.round:
                logger.debug(
                    f'Discarding stale vote from round {vote.round} '
                    f'(current round {game_state.round})'
                )
                continue
            votes.append(vote)

        logger.info(f'Collected {len(votes)}/{expected} {suffix} votes')
        return votes

    async def _wait_for_host_decision(self, votes: list[VoteEvent]) -> int | None:
        """Block until the host submits a decision, then resolve the elimination.

        Args:
            votes: Day votes for majority resolution (used for APPROVE action).

        Returns:
            int: agent_id to eliminate, or None if no elimination.

        TODO: raise if no elimination
        TODO: test me

        """
        self.shared.host_decision_event.clear()
        self.shared.host_decision.action = HostDecisionAction.NOTHING
        await self.shared.host_decision_event.wait()
        if self.shared.host_decision.action == HostDecisionAction.APPROVE:
            return resolve_votes(votes=votes)
        if (
            self.shared.host_decision.action == HostDecisionAction.REJECT
            or self.shared.host_decision.action == HostDecisionAction.NOTHING
        ):
            return None
        if self.shared.host_decision.action == HostDecisionAction.OVERRIDE:
            return self.shared.host_decision.target_id

    async def _check_and_handle_win(self) -> bool:
        """Check win conditions and set GAME_OVER phase if the game has ended.

        Returns:
            True if the game is over, False if it should continue.

        TODO: test me, concurent

        """
        if self._game_active:
            agents_count = await self.db.get_agents_count(
                game_id=self.shared.game_id,
                status=AgentStatus.ALIVE,
            )

            if agents_count.mafia == 0:
                logger.info('Citizens win: all mafia agents eliminated')
                await self.db.update_game_phase(
                    game_id=self.shared.game_id,
                    phase=GamePhase.GAME_OVER,
                )
                self._game_active = False
                return True

            if agents_count.cityzen <= agents_count.mafia:
                logger.info('Mafia wins: citizens are outnumbered')
                await self.db.update_game_phase(
                    game_id=self.shared.game_id,
                    phase=GamePhase.GAME_OVER,
                )
                self._game_active = False
                return True

        return False

    def _drain_vote_queue(self) -> None:
        """Discard any votes left in the queue from previous phases."""
        drained = 0
        while not self.shared.vote_queue.empty():
            try:
                self.shared.vote_queue.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logger.debug(f'Drained {drained} stale votes from queue')
