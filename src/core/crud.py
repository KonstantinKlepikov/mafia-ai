import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiofiles
import aiosqlite
import yaml
from aiofiles import os as aos
from async_lru import alru_cache
from loguru import logger

from schemas import (
    AgentCount,
    AgentState,
    AgentStateInit,
    AgentStatus,
    AgentSummary,
    GamePhase,
    GameState,
    Message,
    MessageItem,
    Persona,
    Role,
    SummaryType,
    SystemPromptKey,
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
                round INTEGER NOT NULL DEFAULT 1,
                phase TEXT NOT NULL DEFAULT 'NIGHT'
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(persona_id) REFERENCES personas(id)
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                round INTEGER NOT NULL,
                phase TEXT NOT NULL,
                target TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agent_states(id)
            )
            """
        )

        # TODO: test me
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS agent_messages_key
            ON agent_messages(agent_id)
            """
        )

        # TODO: test me
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL UNIQUE,
                messages TEXT NOT NULL,
                questions TEXT NOT NULL,
                answers TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agent_states(id)
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_system_prompts_key
            ON system_prompts(key)
            """
        )

        await conn.commit()

    async def init_from_yaml(self, yaml_path: Path) -> list[int]:
        """Load personas from YAML config into database. System is olways first.

        Args:
            yaml_path (Path): Path to prompts.yaml config file.

        Raises:
            FileNotFoundError: If yaml_path does not exist.

        Returns:
            list[int]: list of personas ids

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

        # insert system prompts (game prompts) into system_prompts table
        game_prompts = config.get('game_prompts', {}) or {}
        for k, v in game_prompts.items():
            await self.conn.execute(
                """
                INSERT INTO system_prompts (key, text)
                VALUES (?, ?)
                """,
                (k, v),
            )

        await self.conn.commit()
        logger.info(
            f'Loaded {len(inserted_ids)} personas and {len(game_prompts)} '
            f' system prompts from {yaml_path}'
        )

        return inserted_ids

    @alru_cache
    async def get_system_prompt(self, key: SystemPromptKey) -> str:
        """Retrieve system prompt text by key.

        Args:
            key (SystemPromptKey): key of system prompt

        Raises:
            ValueError: prompt with given key is not found.

        """
        cursor = await self.conn.execute(
            'SELECT text FROM system_prompts WHERE key = ?',
            (key.value,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'System prompt not found: {key.value}')

        return row['text']

    @alru_cache
    async def get_persona(self, persona_id: int) -> Persona:
        """Retrieve a persona by ID.

        Args:
            persona_id (int): persona identifier.

        Raises:
            ValueError: If persona not found.

        Returns:
            Persona

        """

        cursor = await self.conn.execute(
            'SELECT id, name, type, prompt FROM personas WHERE id = ?',
            (persona_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'Persona not found: {persona_id}')

        return Persona(
            persona_id=row['id'],
            name=row['name'],
            persona_type=row['type'],
            prompt=row['prompt'],
        )

    @alru_cache
    async def get_personas(self) -> list[Persona]:
        """Return all personas in database.

        Returns:
            list[Persona]: List of Persona objects.

        """

        cursor = await self.conn.execute(
            'SELECT id, name, type, prompt FROM personas ORDER BY id'
        )
        rows = await cursor.fetchall()

        return [
            Persona(
                persona_id=row['id'],
                name=row['name'],
                persona_type=row['type'],
                prompt=row['prompt'],
            )
            for row in rows
        ]

    async def clear(self) -> None:
        """Delete all temporal game data

        TODO: test me

        """
        await self.conn.execute('PRAGMA foreign_keys = OFF')
        await self.conn.commit()
        cursor = await self.conn.execute(
            """SELECT name FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%'
            AND name <> 'personas'
            AND name <> 'system_prompts'
            """
        )
        rows = await cursor.fetchall()
        table_names = [r[0] for r in rows]

        # Prefer deleting child tables first to avoid foreign key constraint errors
        preferred_order = [
            'agent_messages',
            'agents_summary',
            'agent_states',
            'game_state',
        ]

        # Delete preferred tables in order if they exist
        for name in preferred_order:
            if name in table_names:
                await self.conn.execute(f'DELETE FROM "{name}"')
                await self.conn.execute(
                    'DELETE FROM sqlite_sequence WHERE name = ?',
                    (name,),
                )
                table_names.remove(name)

        # Delete any remaining tables
        for name in table_names:
            await self.conn.execute(f'DELETE FROM "{name}"')
            await self.conn.execute(
                'DELETE FROM sqlite_sequence WHERE name = ?',
                (name,),
            )

        await self.conn.commit()
        await self.conn.execute('PRAGMA foreign_keys = ON')
        await self.conn.commit()
        await self.conn.execute('VACUUM')

    async def init_game(self) -> None:
        """Insert new started game with round 1 and phase NIGHT."""
        await self.conn.execute(
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

    async def update_game(self, round: int, phase: GamePhase) -> None:
        """Update game state.

        Args:
            round (int): Current round number.
            phase (GamePhase): Current game phase.

        """
        await self.conn.execute(
            """
            UPDATE game_state
            SET round = ?, phase = ?
            """,
            (
                round,
                phase.value,
            ),
        )
        await self.conn.commit()

    async def update_game_phase(self, phase: GamePhase) -> None:
        """Update game state.

        Args:
            phase: Current game phase.

        """
        await self.conn.execute(
            """
            UPDATE game_state
            SET phase = ?
            """,
            (phase.value,),
        )
        await self.conn.commit()

    async def update_game_round(self, round: int) -> None:
        """Update game state.

        Args:
            round (int): Current round number.

        """
        await self.conn.execute(
            """
            UPDATE game_state
            SET round = ?
            """,
            (round,),
        )
        await self.conn.commit()

    async def get_game_state(self) -> GameState:
        """Get game state by ID.

        Returns:
            GameState.

        """
        cursor = await self.conn.execute(
            """
            SELECT
                gs.round as round,
                gs.phase as phase,
                group_concat(
                    CASE WHEN st.status = 'ALIVE' THEN st.id END, ','
                ) as alive,
                group_concat(
                    CASE WHEN st.status = 'ELIMINATED' THEN st.id END, ','
                ) as eliminated,
                group_concat(
                    CASE WHEN st.role = 'MAFIA'
                    AND st.status = 'ALIVE'
                    THEN st.id END, ','
                ) as mafia,
                group_concat(
                    CASE WHEN st.role = 'CITIZEN'
                    AND st.status = 'ALIVE'
                    THEN st.id END, ','
                ) as citizen
            FROM game_state gs
            LEFT JOIN agent_states st ON st.role <> 'SYSTEM'
             """
        )
        row = await cursor.fetchone()

        # parse strings produced by group_concat
        alive = [int(x) for x in row['alive'].split(',')] if row['alive'] else []
        eliminated = (
            [int(x) for x in row['eliminated'].split(',')] if row['eliminated'] else []
        )
        mafia = [int(x) for x in row['mafia'].split(',')] if row['mafia'] else []
        citizen = [int(x) for x in row['citizen'].split(',')] if row['citizen'] else []

        return GameState(
            round=row['round'],
            phase=GamePhase(row['phase']),
            alive=alive,
            eliminated=eliminated,
            mafia=mafia,
            citizen=citizen,
        )

    async def init_agent(self, state: AgentStateInit) -> int:
        """Insert new agent.

        Args:
            state (AgentStateInit): AgentState to persist.

        Returns:
            int: agent ID.

        """
        cursor = await self.conn.execute(
            """
            INSERT INTO agent_states (role, status, persona_id)
            VALUES (?, ?, ?)
            """,
            (
                state.role.value,
                state.status.value,
                state.persona_id,
            ),
        )

        cursor = await self.conn.execute('SELECT last_insert_rowid() as agent_id')
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError('Failed to create agent')

        new_agent_id = row['agent_id']

        await self.conn.execute(
            """
            INSERT INTO agents_summary (agent_id, messages, questions, answers)
            VALUES (?, '', '', '')
            """,
            (new_agent_id,),
        )

        await self.conn.commit()
        return new_agent_id

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
            (agent_id, content, round, phase, target)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message.agent_id,
                message.content,
                message.round,
                message.phase,
                message.target.value,
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
            SELECT agent_id, content, round, phase, target
            FROM agent_messages WHERE agent_id = ?
            ORDER BY id
            """,
            (agent_id,),
        )

        msg_rows = await cursor.fetchall()
        messages: list[Message] = []

        for mr in msg_rows:
            msg_dict = {
                'agent_id': mr['agent_id'],
                'content': mr['content'],
                'round': mr['round'],
                'phase': mr['phase'],
                'target': mr['target'],
            }
            messages.append(Message.model_validate(msg_dict))
        return messages

    async def get_last_conversation(self, limit: int) -> list[MessageItem]:
        """Get last messages from current conversation as MessageItem list.

        Args:
            limit (int): number of messages.

        Returns:
            list[MessageItem]: message hystory with agent names.

        TODO: test me

        """
        cursor = await self.conn.execute(
            """
            SELECT am.agent_id, am.content, am.round, am.phase, am.target,
                   p.name as agent_name
            FROM agent_messages am
            LEFT JOIN agent_states st ON st.id = am.agent_id
            LEFT JOIN personas p ON p.id = st.persona_id
            ORDER BY am.id DESC
            LIMIT ?
            """,
            (limit,),
        )

        msg_rows = await cursor.fetchall()
        messages: list[MessageItem] = []

        for mr in msg_rows:
            msg_dict = {'agent_name': mr['agent_name'], 'content': mr['content']}
            messages.append(MessageItem.model_validate(msg_dict))

        # return in chronological order (oldest first)
        return list(reversed(messages))

    async def get_agent_state(self, agent_id: int) -> AgentState:
        """Get agent state and messages by ID.

        Args:
            agent_id (int): agent identifier.

        Returns:
            AgentState.

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
                            'agent_id', am.agent_id,
                            'content', am.content,
                            'round', am.round,
                            'phase', am.phase,
                            'target', am.target
                        ) END
                ) as messages
            FROM agent_states st
            LEFT JOIN agent_messages am ON st.id = am.agent_id
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
                if not isinstance(parsed, list):
                    parsed = []
            except Exception:
                parsed = []

            logger.debug(f'parsed messages: {parsed}')

            messages = [Message.model_validate(m) for m in parsed if m is not None]

        return AgentState(
            agent_id=row['id'],
            role=Role(row['role']),
            persona_id=row['persona_id'],
            status=AgentStatus(row['status']),
            message_history=messages,
        )

    async def get_agents_state(self, status: AgentStatus) -> list[AgentState]:
        """Get states for agents in a game, aggregating messages.

        Args:
            status (AgentStatus): agent status for filtering.

        Returns:
            list[AgentState]: states for alive agents in the game.

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
                                'agent_id', am.agent_id,
                                'content', am.content,
                                'round', am.round,
                                'phase', am.phase,
                                'target', am.target
                            ) END
                    ) as messages
                FROM agent_states st
                LEFT JOIN agent_messages am ON st.id = am.agent_id
                WHERE st.status = ? AND st.role <> "SYSTEM"
            GROUP BY st.id
            ORDER BY st.id
            """,
            (status.value,),
        )

        rows = await cursor.fetchall()
        agents: list[AgentState] = []

        for row in rows:
            msgs_json = row['messages']
            if not msgs_json:
                messages: list[Message] = []
            else:
                try:
                    parsed = json.loads(msgs_json)
                except Exception:
                    parsed = []

                messages = [Message.model_validate(m) for m in parsed if m]

            agents.append(
                AgentState(
                    agent_id=row['id'],
                    role=Role(row['role']),
                    persona_id=row['persona_id'],
                    status=AgentStatus(row['status']),
                    message_history=messages,
                )
            )

        return agents

    async def get_agents_ids(self, status: AgentStatus) -> list[int]:
        """Get ids for agents in a game.

        Args:
            status (AgentStatus): agent status for filtering.

        Returns:
            list[int]: ids of agents.

        """
        cursor = await self.conn.execute(
            """
            SELECT id
            FROM agent_states
            WHERE status = ? AND role <> 'SYSTEM'
            ORDER BY id
            """,
            (status.value,),
        )

        rows = await cursor.fetchall()
        return [row['id'] for row in rows]

    async def get_mafia_ids(self, status: AgentStatus) -> list[int]:
        """Get ids for mafia agents in a game.

        Args:
            status (AgentStatus): agent status for filtering.

        Returns:
            list[int]: ids of agents.

        """
        cursor = await self.conn.execute(
            """
            SELECT id
            FROM agent_states
            WHERE status = ? AND role = 'MAFIA'
            ORDER BY id
            """,
            (status.value,),
        )

        rows = await cursor.fetchall()
        return [row['id'] for row in rows]

    async def get_agents_count(self, status: AgentStatus) -> AgentCount:
        """Get citizen and mafia count.

        Args:
            status (AgentStatus): agent status for filtering.

        Returns:
            AgentCount.

        """
        cursor = await self.conn.execute(
            """
            SELECT
                COALESCE(
                    SUM(CASE WHEN role = 'MAFIA' THEN 1 ELSE 0 END), 0
                ) AS mafia,
                COALESCE(
                    SUM(CASE WHEN role = 'CITIZEN' THEN 1 ELSE 0 END), 0
                ) AS citizen
            FROM agent_states
            WHERE status = ?
            """,
            (status.value,),
        )

        row = await cursor.fetchone()

        return AgentCount(
            mafia=row['mafia'],  # type: ignore[index]
            citizen=row['citizen'],  # type: ignore[index]
        )

    async def get_agent_summary(self, agent_id: int) -> AgentSummary:
        """Get conversations summary of agent

        Args:
            agent_id (int): agent id

        Raises:
            ValueError: agent summary not found

        Returns:
            AgentSummary: summary

        """
        cursor = await self.conn.execute(
            """
            SELECT
                messages, questions, answers
            FROM agents_summary
            WHERE agent_id = ?
            """,
            (agent_id,),
        )

        row = await cursor.fetchone()

        if row is None:
            raise ValueError(f'Agent summary not found: {agent_id}')

        return AgentSummary(
            agent_id=agent_id,
            messages=row['messages'],  # type: ignore[index]
            questions=row['questions'],  # type: ignore[index]
            answers=row['answers'],  # type: ignore[index]
        )

    async def update_agent_summary(
        self,
        agent_id: int,
        summary: str,
        summary_type: SummaryType,
    ) -> None:
        """Update conversations summary of agent

        Args:
            agent_id (int): agent id
            summary (str): text to update
            summary_type (SummaryType): type of updated summarization

        """
        await self.conn.execute(
            f"""
            UPDATE agents_summary
            SET {summary_type.value} = ?
            WHERE agent_id = ?
            """,
            (summary, agent_id),
        )

        await self.conn.commit()
