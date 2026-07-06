from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import AdminFletSettings, MafiaServiceSettings
from data.database import Database
from di_containers import Container
from schemas.game_schemas import GamePhase, GameState
from ui.main_app import MafiaAdminApp


class DbContextManager:
    def __init__(self, db: Database):
        self.db = db

    async def __aenter__(self):
        await self.db.connect()
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.db.close()
        return False


@pytest.fixture(scope='session')
def mock_orchestrator_svc() -> MagicMock:
    """Mocked OrchestratorService for orchestrator API tests."""
    svc = MagicMock()
    svc.begin_game = AsyncMock()
    svc.get_game_state = MagicMock(
        return_value=GameState(
            round=0,
            phase=GamePhase.DAY,
            alive_agents=[],
            eliminated=[],
        )
    )
    svc.submit_host_decision = MagicMock()
    svc.get_agents_info = AsyncMock(return_value={})
    svc.get_agent_info = AsyncMock(return_value=None)
    svc.ask_agent = AsyncMock()
    svc.force_stop_agent = AsyncMock()
    return svc


@pytest.fixture(scope='session')
def settings() -> MafiaServiceSettings:
    """Override settings"""
    config_dict = {}  # type: ignore
    return MafiaServiceSettings(**config_dict)  # type: ignore


@pytest.fixture(scope='session')
def ui_settings() -> AdminFletSettings:
    """Override settings"""
    config_dict = {}  # type: ignore
    return AdminFletSettings(**config_dict)  # type: ignore


@pytest.fixture(scope='function')
async def db(settings: MafiaServiceSettings) -> AsyncGenerator[Database, None]:
    """Override settings"""
    async with DbContextManager(Database()) as db:
        personas_id = await db.init_from_yaml(settings.db_yaml_path)
        assert len(personas_id) == 11, 'wrong personas inited'
        yield db


@pytest.fixture(scope='session')
def container(
    settings: MafiaServiceSettings,
    ui_settings: AdminFletSettings,
) -> Container:
    """Override container"""
    container = Container()
    container.settings.override(settings)
    container.ui_settings.override(ui_settings)
    return container


@pytest.fixture(scope='session')
def app(container: Container) -> MafiaAdminApp:
    """Override container"""
    return MafiaAdminApp()
