import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models import GamePhase, GameState

os.environ['OTEL_SDK_DISABLED'] = 'true'


@pytest.fixture
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
