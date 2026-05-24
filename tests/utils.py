from shared.models import GamePhase, GameState, PersonaType, SystemPrompt


def make_persona(name: str, _type: PersonaType, _id: str, prompt: str) -> SystemPrompt:
    return SystemPrompt(
        persona_id=_id,
        name=name,
        persona_type=_type,
        prompt=prompt,
    )


def game_state(
    phase: GamePhase = GamePhase.DAY,
    alive: list[str] | None = None,
    eliminated: list[str] | None = None,
    round: int = 1,
) -> GameState:
    return GameState(
        round=round,
        phase=phase,
        alive_agents=alive or ['agent-1', 'agent-2', 'agent-3'],
        eliminated=eliminated or [],
    )
