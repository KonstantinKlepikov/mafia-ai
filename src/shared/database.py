import asyncio
import json
from pathlib import Path
from typing import Any

import aiofiles
import aiosqlite
import yaml
from aiofiles import os as aos
from loguru import logger

from .models import AgentRole, AgentState, AgentStatus, GamePhase, SystemPrompt


class Database:
    """Async SQLite in-memory database wrapper.

    DB Stores:
    - Personas (loaded from YAML config)
    - Game state (current round, phase, alive/eliminated agents)
    - Agent states (role, status, persona_id, message_history)

    Provides CRUD operations for personas, game state, and agent states.
    All data is stored in-memory (`:memory:`) by default for fast access
    and automatic cleanup on service restart.

    Args:
        db_path: SQLite database path. Defaults to `:memory:` (in-memory).

    """

    def __init__(self, db_path: str = ':memory:') -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Db connection"""
        if self._conn is None:
            loop = asyncio.get_running_loop()
            loop.create_task(self.connect())
        return self._conn  # type: ignore[return-value]

    async def connect(self) -> None:
        """Open database connection and create schema."""
        if self._conn is not None:
            return

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_schema()
        logger.info(f'Database connected: {self._db_path}')

    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info('Database closed')

    async def _create_schema(self) -> None:
        """Create tables for personas, game_state, and agent_states.

        Raises:
            RuntimeError: Database not connected

        """
        if self._conn is None:
            raise RuntimeError('Database not connected')

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personas (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                prompt TEXT NOT NULL
            )
            """
        )

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_state (
                game_id TEXT PRIMARY KEY,
                round INTEGER NOT NULL,
                phase TEXT NOT NULL,
                alive_agents TEXT NOT NULL,
                eliminated TEXT NOT NULL
            )
            """
        )

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_states (
                agent_id TEXT PRIMARY KEY,
                game_id TEXT,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                persona_id TEXT,
                message_history TEXT NOT NULL,
                FOREIGN KEY(persona_id) REFERENCES personas(id)
            )
            """
        )

        await self._conn.commit()

    async def init_from_yaml(self, yaml_path: str | Path) -> None:
        """Load personas from YAML config into database.

        Args:
            yaml_path: Path to prompts.yaml config file.

        Raises:
            FileNotFoundError: If yaml_path does not exist.

        """
        yaml_path = Path(yaml_path)
        if not await aos.path.exists(yaml_path):
            raise FileNotFoundError(f'Config file not found: {yaml_path}')

        async with aiofiles.open(yaml_path, 'r', encoding='utf-8') as f:
            content = await f.read()

        config = await asyncio.to_thread(yaml.safe_load, content)

        personas = config.get('personas', [])
        if not personas:
            logger.warning('No personas found in YAML config')
            return

        for persona_data in personas:
            await self.conn.execute(
                """
                INSERT OR REPLACE INTO personas (id, name, type, prompt)
                VALUES (?, ?, ?, ?)
                """,
                (
                    persona_data['id'],
                    persona_data['name'],
                    persona_data['type'],
                    persona_data['prompt'],
                ),
            )

        await self.conn.commit()
        logger.info(f'Loaded {len(personas)} personas from {yaml_path}')

    async def get_persona(self, persona_id: str) -> SystemPrompt:
        """Retrieve a persona by ID.

        Args:
            persona_id: Persona identifier (e.g. 'persona-1').

        Returns:
            SystemPrompt populated from database.

        Raises:
            ValueError: If persona not found.

        """

        cursor = await self.conn.execute(
            'SELECT id, name, type, prompt FROM personas WHERE id = ?',
            (persona_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'Persona not found: {persona_id}')

        return SystemPrompt(
            persona_id=row['id'],
            name=row['name'],
            persona_type=row['type'],
            prompt=row['prompt'],
        )

    async def list_personas(self) -> list[SystemPrompt]:
        """Return all personas in database.

        Returns:
            List of SystemPrompt objects.

        """

        cursor = await self.conn.execute(
            'SELECT id, name, type, prompt FROM personas ORDER BY id'
        )
        rows = await cursor.fetchall()

        return [
            SystemPrompt(
                persona_id=row['id'],
                name=row['name'],
                persona_type=row['type'],
                prompt=row['prompt'],
            )
            for row in rows
        ]

    async def upsert_agent_state(self, agent_id: str, state: AgentState) -> None:
        """Insert or update agent state.

        Args:
            agent_id: Agent identifier (e.g. 'agent-1').
            state: AgentState to persist.

        """
        message_history_json = json.dumps(
            [msg.model_dump() for msg in state.message_history]
        )

        await self.conn.execute(
            """
            INSERT OR REPLACE INTO agent_states
            (agent_id, game_id, role, status, persona_id, message_history)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                'game-1',  # Single game for now
                state.role.value,
                AgentStatus.ALIVE.value,  # Default to ALIVE
                state.persona_id,
                message_history_json,
            ),
        )

        await self.conn.commit()

    async def get_agent_state(self, agent_id: str) -> AgentState | None:
        """Retrieve agent state by ID.

        Args:
            agent_id: Agent identifier (e.g. 'agent-1').

        Returns:
            AgentState if found, None otherwise.

        """
        cursor = await self.conn.execute(
            """
            SELECT agent_id, role, status, persona_id, message_history
            FROM agent_states WHERE agent_id = ?
            """,
            (agent_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        from .models import Message

        message_history = [
            Message.model_validate(msg_dict)
            for msg_dict in json.loads(row['message_history'])
        ]

        return AgentState(
            agent_id=row['agent_id'],
            role=AgentRole(row['role']),
            persona_id=row['persona_id'],
            message_history=message_history,
        )

    async def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status (ALIVE or ELIMINATED).

        Args:
            agent_id: Agent identifier.
            status: New status.

        """
        await self.conn.execute(
            'UPDATE agent_states SET status = ? WHERE agent_id = ?',
            (status.value, agent_id),
        )
        await self.conn.commit()

    async def upsert_game_state(
        self,
        game_id: str,
        round_num: int,
        phase: GamePhase,
        alive_agents: list[str],
        eliminated: list[str],
    ) -> None:
        """Insert or update game state.

        Args:
            game_id: Game identifier.
            round_num: Current round number.
            phase: Current game phase.
            alive_agents: List of living agent IDs.
            eliminated: List of eliminated agent IDs.

        """
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO game_state
            (game_id, round, phase, alive_agents, eliminated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                game_id,
                round_num,
                phase.value,
                json.dumps(alive_agents),
                json.dumps(eliminated),
            ),
        )
        await self.conn.commit()

    async def get_game_state(self, game_id: str) -> dict[str, Any] | None:
        """Retrieve game state by ID.

        Args:
            game_id: Game identifier.

        Returns:
            Dict with game_id, round, phase, alive_agents, eliminated, or None.

        """
        cursor = await self.conn.execute(
            """
            SELECT game_id, round, phase, alive_agents, eliminated
            FROM game_state WHERE game_id = ?
            """,
            (game_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return {
            'game_id': row['game_id'],
            'round': row['round'],
            'phase': GamePhase(row['phase']),
            'alive_agents': json.loads(row['alive_agents']),
            'eliminated': json.loads(row['eliminated']),
        }
