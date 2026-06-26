import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiofiles
import aiosqlite
import yaml
from aiofiles import os as aos
from loguru import logger

from .models import (
    AgentCount,
    AgentRole,
    AgentStateIn,
    AgentStateOut,
    AgentStatus,
    GamePhase,
    GameState,
    Message,
    SystemPrompt,
)


class Database:
    """Async SQLite database wrapper.

    NOTE: DB Stores

    - Personas (loaded from YAML config)
    - Game state
    - Agent states
    - Agent messages

    Provides CRUD operations for personas, game state, and agent states.
    All data is stored in-memory by default for fast access
    and automatic cleanup on service restart.

    Args:
        db_path: SQLite database path. Defaults to `:memory:` (in-memory).

    """

    def __init__(self, db_path: str = ':memory:') -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def mconn(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Db connection contexted"""
        yield self.conn
        await self.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        """Db connection"""
        if self._conn is None:
            loop = asyncio.get_running_loop()
            loop.create_task(self.connect())
        return self._conn  # type: ignore[return-value]

    async def connect(self) -> None:
        """Open database connection and create schema."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._create_schema(conn=self._conn)
            logger.info(f'Database connected: {self._db_path}')

    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info('Database closed')

    async def commit(self) -> None:
        await self.conn.commit()

    @staticmethod
    async def _create_schema(conn: aiosqlite.Connection) -> None:
        """Create tables for personas, game_state, and agent_states.

        Raises:
            RuntimeError: Database not connected

        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                prompt TEXT NOT NULL
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                phase TEXT NOT NULL
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(persona_id) REFERENCES personas(id),
                FOREIGN KEY(game_id) REFERENCES game_state(id)
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                round INTEGER NOT NULL,
                phase INTEGER NOT NULL,
                target_audience TEXT NOT NULL,
                FOREIGN KEY(sender_id) REFERENCES agent_states(id)
            )
            """
        )

        await conn.commit()

    async def init_personas_from_yaml(self, yaml_path: Path) -> list[int]:
        """Load personas from YAML config into database. System is olways first.

        Args:
            yaml_path (Path): Path to prompts.yaml config file.

        Raises:
            FileNotFoundError: If yaml_path does not exist.

        Returns:
            ;ist[int]: list of personas ids

        """
        if not await aos.path.exists(yaml_path):
            raise FileNotFoundError(f'Config file not found: {yaml_path}')

        async with aiofiles.open(yaml_path, 'r', encoding='utf-8') as f:
            content = await f.read()

        config = await asyncio.to_thread(yaml.safe_load, content)

        inserted_ids: list[int] = []

        for persona_data in config.get('personas', []):
            cursor = await self.conn.execute(
                """
                INSERT INTO personas (name, type, prompt)
                VALUES (?, ?, ?)
                """,
                (
                    persona_data['name'],
                    persona_data['type'],
                    persona_data['prompt'],
                ),
            )
            inserted_ids.append(cursor.lastrowid)  # type: ignore[arg-type]

        await self.conn.commit()
        logger.info(f'Loaded {len(inserted_ids)} personas from {yaml_path}')

        return inserted_ids

    async def get_persona(self, persona_id: int) -> SystemPrompt:
        """Retrieve a persona by ID.

        Args:
            persona_id (int): persona identifier.

        Raises:
            ValueError: If persona not found.

        Returns:
            SystemPrompt

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

    async def get_personas(self) -> list[SystemPrompt]:
        """Return all personas in database.

        Returns:
            list[SystemPrompt]: List of SystemPrompt objects.

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

    async def init_game(self) -> int:
        """Insert new started game with round 1 and phase NIGHT.

        Returns:
            int: current game ID.

        """
        cursor = await self.conn.execute(
            """
            INSERT INTO game_state
            (round, phase)
            VALUES (?, ?)
            """,
            (
                1,
                GamePhase.NIGHT.value,
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def update_game(self, game_id: int, round: int, phase: GamePhase) -> None:
        """Update game state.

        Args:
            game_id: Game identifier.
            round_num: Current round number.
            phase: Current game phase.

        """
        await self.conn.execute(
            """
            REPLACE INTO game_state
            (id, round, phase)
            VALUES (?, ?, ?)
            """,
            (
                game_id,
                round,
                phase.value,
            ),
        )
        await self.conn.commit()

    async def update_game_phase(self, game_id: int, phase: GamePhase) -> None:
        """Update game state.

        Args:
            game_id: Game identifier.
            phase: Current game phase.

        TODO: test me

        """
        await self.conn.execute(
            """
            REPLACE INTO game_state
            (id, phase)
            VALUES (?, ?)
            """,
            (
                game_id,
                phase.value,
            ),
        )
        await self.conn.commit()

    async def update_round(self, game_id: int, round: int) -> None:
        """Update game state.

        Args:
            game_id: Game identifier.
            round_num: Current round number.

        TODO: test me

        """
        await self.conn.execute(
            """
            REPLACE INTO game_state
            (id, round)
            VALUES (?, ?)
            """,
            (
                game_id,
                round,
            ),
        )
        await self.conn.commit()

    async def get_game_state(self, game_id: int) -> GameState:
        """Get game state by ID.

        Args:
            game_id (int): game identifier.

        Returns:
            GameState.

        TODO: test me

        """
        cursor = await self.conn.execute(
            """
            SELECT
                gs.id as id,
                gs.round as round,
                gs.phase as phase,
                group_concat(
                    CASE WHEN st.status = 'ALIVE' THEN st.id END, ','
                ) as alive,
                group_concat(
                    CASE WHEN st.status = 'ELIMINATED' THEN st.id END, ','
                ) as eliminated
            FROM game_state gs
            LEFT JOIN agent_states st ON gs.id = st.game_id AND st.role <> 'SYSTEM'
            WHERE gs.id = ?
            GROUP BY gs.id
            """,
            (game_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'Game not found: {game_id}')

        # parse CSV strings produced by group_concat (may be None or empty)
        alive_csv = row['alive']
        eliminated_csv = row['eliminated']

        alive = [int(x) for x in alive_csv.split(',')] if alive_csv else []
        eliminated = (
            [int(x) for x in eliminated_csv.split(',')] if eliminated_csv else []
        )

        return GameState(
            game_id=row['id'],
            round=row['round'],
            phase=GamePhase(row['phase']),
            alive=alive,
            eliminated=eliminated,
        )

    async def init_agent(self, state: AgentStateIn, game_id: int) -> int:
        """Insert new agent.

        Args:
            state (AgentStateIn): AgentState to persist.
            game_id (int): current game.

        Returns:
            int: agent ID.

        """
        cursor = await self.conn.execute(
            """
            INSERT INTO agent_states
            (game_id, role, status, persona_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                game_id,
                state.role.value,
                state.status.value,
                state.persona_id,
            ),
        )

        await self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def update_agent_status(self, agent_id: int, status: AgentStatus) -> None:
        """Update agent status (ALIVE or ELIMINATED).

        Args:
            agent_id (int): Agent identifier.
            status (AgentStatus): New status.

        """
        await self.conn.execute(
            'UPDATE agent_states SET status = ? WHERE id = ?',
            (status.value, agent_id),
        )
        await self.conn.commit()

    async def insert_message(self, message: Message) -> int:
        """Insert agent message

        Args:
            message (Message): message

        Returns:
            int: messge ID.

        """
        cursor = await self.conn.execute(
            """
            INSERT INTO agent_messages
            (sender_id, content, round, phase, target_audience)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message.sender_id,
                message.content,
                message.round,
                message.phase,
                message.target_audience.value,
            ),
        )

        await self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_message_hystory(self, agent_id: int) -> list[Message]:
        """Get messages of agent.

        Args:
            agent_id (int): agent identifier.

        Returns:
            list[Message]: message hystory.

        """
        cursor = await self.conn.execute(
            """
            SELECT sender_id, content, round, phase, target_audience
            FROM agent_messages WHERE sender_id = ?
            ORDER BY id
            """,
            (agent_id,),
        )

        msg_rows = await cursor.fetchall()
        messages: list[Message] = []

        for mr in msg_rows:
            msg_dict = {
                'sender_id': mr['sender_id'],
                'content': mr['content'],
                'round': mr['round'],
                'phase': mr['phase'],
                'target_audience': mr['target_audience'],
            }
            messages.append(Message.model_validate(msg_dict))
        return messages

    async def get_agent_state(self, agent_id: int) -> AgentStateOut:
        """Get agent state and messages by ID.

        Args:
            agent_id (int): agent identifier.

        Returns:
            AgentStateOut.

        """
        cursor = await self.conn.execute(
            """
            SELECT
                st.id as id,
                st.role as role,
                st.status as status,
                st.persona_id as persona_id,
                json_group_array(
                    CASE WHEN am.id IS NOT NULL THEN
                        json_object(
                            'sender_id', am.sender_id,
                            'content', am.content,
                            'round', am.round,
                            'phase', am.phase,
                            'target_audience', am.target_audience
                        ) END
                ) as messages
            FROM agent_states st
            LEFT JOIN agent_messages am ON st.id = am.sender_id
            WHERE st.id = ?
            GROUP BY st.id
            """,
            (agent_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'Agent not found: {agent_id}')

        msgs_json = row['messages']
        if not msgs_json:
            messages: list[Message] = []
        else:
            try:
                parsed = json.loads(msgs_json)
            except Exception:
                parsed = []

            messages = [Message.model_validate(m) for m in parsed]

        return AgentStateOut(
            agent_id=row['id'],
            role=AgentRole(row['role']),
            persona_id=row['persona_id'],
            status=AgentStatus(row['status']),
            message_history=messages,
        )

    async def get_agents_state(
        self,
        game_id: int,
        status: AgentStatus,
    ) -> list[AgentStateOut]:
        """Get states for agents in a game, aggregating messages.

        Args:
            game_id (int): game identifier.

        Returns:
            list[AgentStateOut]: states for alive agents in the game.

        """
        cursor = await self.conn.execute(
            """
            SELECT
                st.id as id,
                st.role as role,
                st.status as status,
                st.persona_id as persona_id,
                json_group_array(
                        CASE WHEN am.id IS NOT NULL THEN
                            json_object(
                                'sender_id', am.sender_id,
                                'content', am.content,
                                'round', am.round,
                                'phase', am.phase,
                                'target_audience', am.target_audience
                            ) END
                    ) as messages
                FROM agent_states st
                LEFT JOIN agent_messages am ON st.id = am.sender_id
                WHERE st.game_id = ? AND st.status = ? AND st.role <> "SYSTEM"
            GROUP BY st.id
            ORDER BY st.id
            """,
            (game_id, status.value),
        )

        rows = await cursor.fetchall()
        agents: list[AgentStateOut] = []

        for row in rows:
            msgs_json = row['messages']
            if not msgs_json:
                messages: list[Message] = []
            else:
                try:
                    parsed = json.loads(msgs_json)
                except Exception:
                    parsed = []

                messages = [Message.model_validate(m) for m in parsed]

            agents.append(
                AgentStateOut(
                    agent_id=row['id'],
                    role=AgentRole(row['role']),
                    persona_id=row['persona_id'],
                    status=AgentStatus(row['status']),
                    message_history=messages,
                )
            )

        return agents

    async def get_agents_ids(
        self,
        game_id: int,
        status: AgentStatus,
    ) -> list[int]:
        """Get ids for agents in a game.

        Args:
            game_id (int): game identifier.
            status (AgentStatus): agent status for filtering.

        Returns:
            list[int]: ids of agents.

        TODO: test me

        """
        cursor = await self.conn.execute(
            """
            SELECT id
            FROM agent_states
            WHERE game_id = ? AND status = ? AND role <> 'SYSTEM'
            ORDER BY id
            """,
            (game_id, status.value),
        )

        rows = await cursor.fetchall()
        return [row['id'] for row in rows]

    async def get_mafia_ids(
        self,
        game_id: int,
        status: AgentStatus,
    ) -> list[int]:
        """Get ids for mafia agents in a game.

        Args:
            game_id (int): game identifier.
            status (AgentStatus): agent status for filtering.

        Returns:
            list[int]: ids of agents.

        TODO: test me

        """
        cursor = await self.conn.execute(
            """
            SELECT id
            FROM agent_states
            WHERE game_id = ? AND status = ? AND role = 'MAFIA'
            ORDER BY id
            """,
            (game_id, status.value),
        )

        rows = await cursor.fetchall()
        return [row['id'] for row in rows]

    async def get_agents_count(
        self,
        game_id: int,
        status: AgentStatus,
    ) -> AgentCount:
        """Get cityzen and mafia count.

        Args:
            game_id (int): game identifier.
            status (AgentStatus): agent status for filtering.

        Returns:
            AgentCount.

        TODO: test me

        """
        cursor = await self.conn.execute(
            """
            SELECT
                SUM(CASE WHEN role = 'MAFIA' THEN 1 ELSE 0 END) AS mafia,
                SUM(CASE WHEN role = 'CITYZEN' THEN 1 ELSE 0 END) AS cityzen
            FROM agent_states
            WHERE game_id = ? AND status = ?
            """,
            (game_id, status.value),
        )

        row = await cursor.fetchone()

        if row is None:
            return AgentCount(mafia=0, cityzen=0)

        return AgentCount(mafia=row['mafia'], cityzen=row['cityzen'])
