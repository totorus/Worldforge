"""Inter-faction relations management."""

from app.simulator.types import WorldState, Relation


def update_relation(state: WorldState, fac_a: str, fac_b: str, event_type: str):
    """Update relation between two factions based on event type."""
    rel = state.get_relation(fac_a, fac_b)

    if rel is None:
        rel = Relation(faction_a=fac_a, faction_b=fac_b, type="neutral", intensity=0.0)
        state.relations.append(rel)

    if event_type == "conflict":
        rel.intensity = min(1.0, rel.intensity + 0.2)
        if rel.intensity > 0.5:
            rel.type = "rivalry"
    elif event_type == "diplomacy":
        rel.intensity = max(0.0, rel.intensity - 0.2)
        if rel.intensity < 0.3:
            rel.type = "alliance" if rel.intensity < 0.15 else "neutral"
        state.trade_routes_active = True


def get_rivalry_intensity(state: WorldState, fac_a: str, fac_b: str) -> float:
    """Get rivalry intensity between two factions (0 = friends, 1 = enemies)."""
    rel = state.get_relation(fac_a, fac_b)
    if rel is None:
        return 0.0
    if rel.type == "rivalry":
        return rel.intensity
    return 0.0
