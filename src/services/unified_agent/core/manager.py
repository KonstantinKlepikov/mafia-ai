from typing import Any

import httpx
from loguru import logger

from shared.database import Database
from shared.models import (
    AgentRole,
    AgentState,
    AgentStatus,
    GamePhase,
    Message,
    SystemPrompt,
)

from .agent_logic import AgentLogic


class AgentManager:
    """Manages all AI agents in a single process.

    Args:
        llm_url: Base URL of the LLM service (e.g. 'http://llm:8003').
        db: Database instance with personas and state storage.

    """

    def __init__(self, llm_url: str, db: Database) -> None:
        self._llm_url = llm_url
        self._db = db
        self._llm_client = httpx.AsyncClient(base_url=llm_url, timeout=60.0)
        self._agents: dict[str, AgentLogic] = {}

    async def initialize_agent(
        self, agent_id: str, role: AgentRole, persona_id: str
    ) -> None:
        """Initialize a new agent with given role and persona.

        Args:
            agent_id: Unique agent identifier (e.g. 'agent-1').
            role: Role assigned (MAFIA or CITIZEN).
            persona_id: ID of persona from config/prompts.yaml.

        Raises:
            ValueError: If persona not found in database.

        """
        persona = await self._db.get_persona(persona_id)

        system_prompt = SystemPrompt(
            persona_id=persona.persona_id,
            name=persona.name,
            persona_type=persona.persona_type,
            prompt=persona.prompt,
        )

        # Create AgentLogic instance
        agent_logic = AgentLogic(
            agent_id=agent_id,
            persona=system_prompt,
            llm_client=self._llm_client,
            db=self._db,
        )
        self._agents[agent_id] = agent_logic

        # Store initial state in DB
        state = AgentState(
            agent_id=agent_id,
            role=role,
            persona_id=persona_id,
            message_history=[],
        )
        await self._db.upsert_agent_state(agent_id, state)

        logger.info(
            f'Agent {agent_id} initialized with role={role}, persona={persona_id}'
        )

    async def act(
        self, agent_id: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an action for a specific agent.

        Args:
            agent_id: Agent to act.
            action: Action type ('generate_message', 'vote',
                'answer_question', 'add_message').
            params: Action-specific parameters.

        Returns:
            Result dictionary with action output.

        Raises:
            ValueError: If agent not initialized or action unknown.

        """
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        agent = self._agents[agent_id]

        if action == 'generate_message':
            phase = GamePhase(params['phase'])
            game_round = int(params['round'])
            text = await agent.generate_message(phase, game_round)
            return {'message': text}

        if action == 'vote':
            candidates = list(params['candidates'])
            is_night = bool(params['is_night'])
            game_round = int(params['round'])
            target = await agent.generate_vote(candidates, is_night, game_round)
            return {'vote_target': target}

        if action == 'answer_question':
            question = str(params['question'])
            answer = await agent.answer_question(question)
            return {'answer': answer}

        if action == 'add_message':
            message_dict = params['message']
            message = Message(**message_dict)
            await agent.add_message_to_history(message)
            return {'status': 'ok'}

        raise ValueError(f'Unknown action: {action}')

    async def get_state(self, agent_id: str) -> AgentState:
        """Get current state of an agent from DB.

        Args:
            agent_id: Agent to query.

        Returns:
            Current agent state from database.

        Raises:
            ValueError: If agent not initialized or not found in DB.

        """
        if agent_id not in self._agents:
            raise ValueError(f'Agent {agent_id} not initialized')

        state = await self._db.get_agent_state(agent_id)
        if state is None:
            raise ValueError(f'Agent {agent_id} state not found in DB')

        return state

    async def eliminate(self, agent_id: str) -> None:
        """Mark agent as eliminated (remove from active agents).

        Args:
            agent_id: Agent to eliminate.

        """
        if agent_id not in self._agents:
            logger.warning(f'Attempted to eliminate non-initialized agent {agent_id}')
            return

        await self._db.update_agent_status(agent_id, AgentStatus.ELIMINATED)
        del self._agents[agent_id]

        logger.info(f'Agent {agent_id} eliminated and removed')

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self._llm_client.aclose()
        logger.info('AgentManager closed')
