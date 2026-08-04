import asyncio
import random
import uuid
from dataclasses import dataclass, field

from loguru import logger

from config import MafiaSettings
from core.llm import LLM
from data import Database
from schemas import (
    Agent,
    AgentAnswer,
    AgentRole,
    AgentStateIn,
    AgentStatus,
    EmptySharingException,
    GamePhase,
    GameState,
    HostDecision,
    HostDecisionAction,
    Message,
    Persona,
    VoteEvent,
)

from .agent_logic import AgentLogic
from .event_bus import EventBus
from .vote_resolver import resolve_votes


@dataclass
class Shared:
    """Cached and shared data of game"""

    # Game state
    all_personas: dict[int, Persona]
    game_id: int
    system_agent_id: int
    mafia_agents_ids: list[int]
    cityzen_agents_ids: list[int]

    # Vote collection
    vote_queue: asyncio.Queue[VoteEvent]

    # Host decision synchronisation
    host_decision: HostDecision
    host_decision_event: asyncio.Event

    # Agents
    agents: dict[int, AgentLogic] = field(default_factory=dict)


class Game:
    """Unified game orchestrator and agent manager.

    Runs an asyncio game loop as a background task once a game is started.
    Manages all AI agents.

    The FSM cycle per round:
    NIGHT → NIGHT_VOTE → RESOLVE_NIGHT → DAY → DAY_VOTE → HOST_DECISION
    → (next NIGHT | GAME_OVER)

    Args:
        settings: Populated MafiaSettings instance.
        llm: LLM for direct local inference.
        event_bus: event bus for UI notifications.
        db: Databse.

    """

    def __init__(
        self,
        settings: MafiaSettings,
        llm: LLM,
        event_bus: EventBus,
        db: Database,
    ) -> None:
        self.settings = settings
        self.db = db
        self.llm = llm
        self.event_bus = event_bus
        self._shared: Shared | None = None
        self._game_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self.game_active: bool = False

    @property
    def shared(self) -> Shared:
        if not self._shared:
            raise EmptySharingException('Game is not started.')
        return self._shared

    @shared.setter
    def shared(self, shared: Shared) -> None:
        self._shared = shared

    @shared.deleter
    def shared(self) -> None:
        self._shared = None

    async def initialize_agent(
        self,
        state: AgentStateIn,
        persona: Persona,
        game_id: int,
    ) -> AgentLogic:
        """Initialize a new agent and register its logic.

        TODO: test me
        """
        agent_id = await self.db.init_agent(state=state, game_id=game_id)
        agent = AgentLogic(
            agent_id=agent_id,
            persona=persona,
            llm=self.llm,
            db=self.db,
            settings=self.settings,
        )
        logger.info(
            f'Agent {agent_id} initialized with '
            f'role={state.role.value}, persona={persona.persona_id}'
        )
        return agent

    async def eliminate_agent(self, agent_id: int) -> None:
        """Mark an agent as eliminated and remove it from the in-memory registry."""
        del self.shared.agents[agent_id]
        await self.db.update_agent_status(
            agent_id=agent_id,
            status=AgentStatus.ELIMINATED,
        )
        logger.info(f'Agent {agent_id} eliminated and removed from AgentLogic')

    async def begin_game(self) -> None:
        """Initialise roles/personas and launch the game loop.

        Raises:
            RuntimeError: If a game is already in progress.

        TODO: test me

        """
        try:
            if self.game_active:
                logger.info('A game is already in progress. ')
            else:
                del self.shared
        except EmptySharingException:
            ...

        self.event_bus.clean()
        all_personas = {p.persona_id: p for p in await self.db.get_personas()}
        game_id = await self.db.init_game()
        logger.debug(f'{game_id=}')

        # roles
        system, mafia, cityzen = self.split_personas(all_personas=all_personas)

        # Initialize agents via agent manager
        # NOTE: is blocked calls, but no matter
        agents: dict[int, AgentLogic] = {}
        system_agent = await self.initialize_agent(
            state=AgentStateIn(
                role=AgentRole.SYSTEM,
                status=AgentStatus.ALIVE,
                persona_id=system,
            ),
            persona=all_personas[system],
            game_id=game_id,
        )
        agents[system_agent.agent_id] = system_agent
        mafia_agents_ids = []
        for m in mafia:
            mafia_agent = await self.initialize_agent(
                state=AgentStateIn(
                    role=AgentRole.MAFIA,
                    status=AgentStatus.ALIVE,
                    persona_id=m,
                ),
                persona=all_personas[m],
                game_id=game_id,
            )
            agents[mafia_agent.agent_id] = mafia_agent
            mafia_agents_ids.append(mafia_agent.agent_id)

        cityzen_agents_ids = []
        for c in cityzen:
            cityzen_agent = await self.initialize_agent(
                state=AgentStateIn(
                    role=AgentRole.CITIZEN,
                    status=AgentStatus.ALIVE,
                    persona_id=c,
                ),
                persona=all_personas[c],
                game_id=game_id,
            )
            agents[cityzen_agent.agent_id] = cityzen_agent
            cityzen_agents_ids.append(cityzen_agent.agent_id)

        self.shared = Shared(
            all_personas=all_personas,
            game_id=game_id,
            system_agent_id=system_agent.agent_id,
            mafia_agents_ids=mafia_agents_ids,
            cityzen_agents_ids=cityzen_agents_ids,
            vote_queue=asyncio.Queue(),
            host_decision=HostDecision(),
            host_decision_event=asyncio.Event(),
            agents=agents,
        )
        logger.debug(f'{self.shared=}')
        self._game_task = asyncio.create_task(self._run_game_loop())
        self.game_active = True
        logger.info('Game begin.')

    async def end_game(self) -> None:
        self.event_bus.clean()
        del self.shared
        if self._game_task is not None and not self._game_task.done():
            self._game_task.cancel()
        logger.info('Game end.')

    def submit_host_decision(self, decision: HostDecision) -> None:
        """Accept a host decision and unblock the waiting game loop.

        Args:
            decision: The host's action and optional override target.

        """
        self.shared.host_decision = decision
        self.shared.host_decision_event.set()

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
                self.shared.agents[agent_id].answer_question(question_text),
                timeout=timeout,
            )

            answer = AgentAnswer(
                question_id=str(uuid.uuid4()),
                agent_id=agent_id,
                answer_text=answer_text,
            )

            self.event_bus.publish(feed=answer)

            return answer_text
        except Exception as exc:
            logger.warning(f'Failed to get answer from {agent_id}: {exc.__str__()}')
            raise

    async def force_stop_agent(self, agent_id: int) -> None:
        """Force-eliminate an agent.

        Args:
            agent_id: ID of the agent to remove from the game.

        """
        await self._eliminate_agent(agent_id)

    @staticmethod
    def split_personas(
        all_personas: dict[int, Persona],
    ) -> tuple[int, list[int], list[int]]:
        """Split personas.

        Returns:
            tuple[int, list[int], list[int]]: system, mafia, cityzen

        TODO: test me

        """
        system = list(all_personas.keys())[0]
        remaining = list(all_personas.keys())[1:]
        mafia = random.sample(remaining, 3)
        cityzen = [p for p in remaining if p != system and p not in mafia]
        return (system, mafia, cityzen)

    async def _run_game_loop(self) -> None:
        """Main finite-state-machine game loop.

        TODO: test me, concurent
        """
        try:
            while self.game_active:
                mafia = await self.db.get_mafia_ids(
                    game_id=self.shared.game_id,
                    status=AgentStatus.ALIVE,
                )
                logger.info('--- NIGHT ---')
                game_state = await self._transition_phase(phase=GamePhase.NIGHT)
                await self._run_speak_phase(mafia_only=True, game_state=game_state)

                logger.info('--- NIGHT_VOTE ---')
                await self._transition_phase(phase=GamePhase.NIGHT_VOTE)
                night_votes = await self._collect_votes(
                    expected=len(mafia),
                    suffix='night',
                )

                logger.info('--- RESOLVE_NIGHT ---')
                game_state = await self._transition_phase(phase=GamePhase.RESOLVE_NIGHT)
                eliminated_id = resolve_votes(votes=night_votes)
                if eliminated_id:
                    await self._eliminate_agent(agent_id=eliminated_id)
                if self._check_and_handle_win():
                    break

                logger.info('--- DAY ---')
                game_state = await self._transition_phase(phase=GamePhase.DAY)
                await self._run_speak_phase(mafia_only=False, game_state=game_state)

                logger.info('--- DAY_VOTE ---')
                await self._transition_phase(phase=GamePhase.DAY_VOTE)
                alive = await self.db.get_agents_ids(
                    game_id=self.shared.game_id,
                    status=AgentStatus.ALIVE,
                )
                day_votes = await self._collect_votes(expected=len(alive), suffix='day')

                logger.info('--- HOST_DECISION ---')
                game_state = await self._transition_phase(phase=GamePhase.HOST_DECISION)
                eliminated_id = await self._wait_for_host_decision(votes=day_votes)
                if eliminated_id:
                    await self._eliminate_agent(agent_id=eliminated_id)
                if self._check_and_handle_win():
                    break

                await self.db.update_game_round(
                    game_id=self.shared.game_id,
                    round=game_state.round + 1,
                )
        except asyncio.CancelledError:
            logger.info('Game loop cancelled')
        finally:
            self.game_active = False
            logger.info('Game loop ended')

    async def _transition_phase(self, phase: GamePhase) -> GameState:
        """Update the phase and broadcast the new game state.

        Args:
            phase (GamePhase): target phase to transition into.

        Returns:
            GameState

        """
        await self.db.update_game_phase(game_id=self.shared.game_id, phase=phase)
        logger.info(f'Phase -> {phase}')
        game_state = await self.db.get_game_state(game_id=self.shared.game_id)
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

        await self.eliminate_agent(agent_id)
        logger.info(f'Agent {agent_id} eliminated')

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

        tasks: list[asyncio.Task] = []
        try:
            async with asyncio.TaskGroup() as tg:
                for agent_id in targets:
                    tasks.append(
                        tg.create_task(
                            self.shared.agents[agent_id].generate_message(
                                phase=game_state.phase,
                                game_round=game_state.round,
                            )
                        )
                    )
        except Exception as exc:
            logger.error(f'Message generation failed: {exc.__str__()}')

        [
            self.event_bus.publish(
                feed=Message(
                    sender_id=agent_id,
                    agent_id=agent_id,
                    round=game_state.round,
                    phase=game_state.phase,
                    content=task.result(),
                )
            )
            for task in tasks
        ]

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
        deadline = loop.time() + self.settings.vote_timeout_seconds

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
        if self.game_active:
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
                self.game_active = False
                return True

            if agents_count.citizen <= agents_count.mafia:
                logger.info('Mafia wins: citizens are outnumbered')
                await self.db.update_game_phase(
                    game_id=self.shared.game_id,
                    phase=GamePhase.GAME_OVER,
                )
                self.game_active = False
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
