from dependency_injector import containers, providers

from config import AdminFletSettings, MafiaServiceSettings
from core.event_bus import EventBus
from core.service import Game
from llm.service import LLM
from shared.database import Database
from ui.subscriber import Subscriber


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            'ui.main_app',
            'ui.ask_agent_panel',
            'ui.game_controls',
        ]
    )

    # game settings
    settings = providers.Singleton(MafiaServiceSettings)
    ui_settings = providers.Singleton(AdminFletSettings)

    # services
    llm = providers.Singleton(LLM, settings=settings)
    event_bus = providers.Singleton(EventBus)
    subscriber = providers.Singleton(Subscriber, event_bus=event_bus)
    db = providers.Singleton(Database)
    game = providers.Singleton(
        Game,
        settings=settings,
        llm=llm,
        event_bus=event_bus,
        db=db,
    )
