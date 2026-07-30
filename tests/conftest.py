from typing import AsyncGenerator

import pytest

from config import AdminFletSettings, MafiaSettings
from core.llm import LLM
from data.database import Database
from di_containers import Container
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
def settings() -> MafiaSettings:
    """Override settings"""
    config_dict = {}  # type: ignore
    return MafiaSettings(**config_dict)  # type: ignore


@pytest.fixture(scope='session')
def ui_settings() -> AdminFletSettings:
    """Override settings"""
    config_dict = {}  # type: ignore
    return AdminFletSettings(**config_dict)  # type: ignore


@pytest.fixture(scope='function')
async def db(settings: MafiaSettings) -> AsyncGenerator[Database, None]:
    """Db"""
    async with DbContextManager(Database()) as db:
        personas_id = await db.init_from_yaml(settings.db_yaml_path)
        assert len(personas_id) == 11, 'wrong personas inited'
        yield db


@pytest.fixture(scope='function')
async def llm(settings: MafiaSettings) -> AsyncGenerator[LLM, None]:
    """Llm"""
    yield LLM(settings=settings)


@pytest.fixture(scope='function')
async def game_id(db: Database) -> int:
    """game"""
    game_id = await db.init_game()
    assert game_id == 1, 'wrong game id'
    return game_id


@pytest.fixture(scope='session')
def container(
    settings: MafiaSettings,
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
