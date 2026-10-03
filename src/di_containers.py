from contextlib import asynccontextmanager

from dependency_injector import containers, providers
from loguru import logger
from ollama import AsyncClient

from config import AdminFletSettings, MafiaSettings
from core import Database, EventBus, Game, setup_logging


@asynccontextmanager
async def init_db(db: Database, settings: MafiaSettings):
    try:
        setup_logging(level=settings.log_level)
        await db.connect()
        logger.info(f'Game engine started, log_level={settings.log_level}')
    except Exception as exc:
        logger.error(f'Game engine failed to start: {exc.__str__()}')
        raise
    yield
    await db.close()
    logger.info('Game engine stopped')


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            'ui.main_app',
            'ui.ask_agent_panel',
            'ui.game_controls',
        ]
    )

    # game settings
    settings = providers.Singleton(MafiaSettings)
    ui_settings = providers.Singleton(AdminFletSettings)

    # services
    ollama = providers.Singleton(AsyncClient)
    event_bus = providers.Singleton(EventBus)
    db = providers.Singleton(Database)
    init_game_engine = providers.Resource(init_db, db=db, settings=settings)
    game = providers.Singleton(
        Game,
        settings=settings,
        event_bus=event_bus,
        db=db,
        ollama=ollama,
    )
