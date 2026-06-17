from unittest.mock import AsyncMock, MagicMock

import pytest

from config import AdminFletSettings, MafiaServiceSettings
from di_containers import Container
from shared.models import GamePhase, GameState
from ui.main_app import MafiaAdminApp


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
