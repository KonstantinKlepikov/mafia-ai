from contextlib import asynccontextmanager

from dependency_injector import containers, providers
from loguru import logger

from config import AdminFletSettings, MafiaSettings
from core.event_bus import EventBus
from core.game import Game
from core.llm import LLM
from data import Database


@asynccontextmanager
async def init_game(db: Database, settings: MafiaSettings):
    try:
        await db.connect()
        await db.init_from_yaml(yaml_path=settings.db_yaml_path)
        logger.info('Game engine started')
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
    llm = providers.Singleton(LLM, settings=settings)
    event_bus = providers.Singleton(EventBus)
    db = providers.Singleton(Database)
    init_game_engine = providers.Resource(init_game, db=db, settings=settings)
    game = providers.Singleton(
        Game,
        settings=settings,
        llm=llm,
        event_bus=event_bus,
        db=db,
    )
