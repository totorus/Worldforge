"""Extensible precondition parser for event evaluation.

Each precondition function receives (state, faction_id_or_none, event_config)
and returns True if the precondition is met.
"""

import re
from typing import Callable

from app.simulator.types import WorldState

# Registry of precondition checkers
_CHECKERS: dict[str, Callable] = {}


def register(name: str):
    """Decorator to register a precondition checker."""
    def decorator(fn):
        _CHECKERS[name] = fn
        return fn
    return decorator


def check_precondition(
    requires: str,
    state: WorldState,
    faction_id: str | None = None,
) -> bool:
    """Check if a precondition string is satisfied.

    Tries exact match first, then pattern-based matchers.
    Returns True if the precondition is met.
    Unknown preconditions return True (permissive for wizard-generated custom ones).
    """
    if requires in _CHECKERS:
        return _CHECKERS[requires](state, faction_id)

    # Pattern-based: any_faction_with_power_affinity_above_X
    m = re.match(r"any_faction_with_power_affinity_above_([\d.]+)", requires)
    if m:
        threshold = float(m.group(1))
        return any(f.attributes.power_affinity > threshold for f in state.factions.values())

    # Pattern-based: faction_with_power_affinity_above_X
    m = re.match(r"faction_with_power_affinity_above_([\d.]+)", requires)
    if m and faction_id:
        threshold = float(m.group(1))
        fac = state.factions.get(faction_id)
        return fac is not None and fac.attributes.power_affinity > threshold

    # Unknown precondition — permissive (wizard may invent new ones)
    return True


# --- Built-in precondition checkers ---

@register("two_adjacent_factions")
def _two_adjacent(state: WorldState, faction_id: str | None) -> bool:
    return len(state.get_adjacent_faction_pairs()) > 0


@register("governance_monarchy_or_chieftain")
def _governance_monarchy_or_chieftain(state: WorldState, faction_id: str | None) -> bool:
    keywords = ("monarchy", "monarch", "chieftain", "tribal_chieftain", "king", "queen")
    if faction_id:
        fac = state.factions.get(faction_id)
        return fac is not None and any(k in fac.governance.lower() for k in keywords)
    return any(any(k in f.governance.lower() for k in keywords) for f in state.factions.values())


@register("governance_theocracy_or_council")
def _governance_theocracy_or_council(state: WorldState, faction_id: str | None) -> bool:
    keywords = ("theocracy", "council", "theocratic", "conseil")
    if faction_id:
        fac = state.factions.get(faction_id)
        return fac is not None and any(k in fac.governance.lower() for k in keywords)
    return any(any(k in f.governance.lower() for k in keywords) for f in state.factions.values())


@register("population_above_70_percent_capacity")
def _pop_above_70(state: WorldState, faction_id: str | None) -> bool:
    for fac in state.factions.values():
        if faction_id and fac.id != faction_id:
            continue
        total_cap = sum(
            state.regions[r].max_population for r in fac.regions if r in state.regions
        )
        if total_cap > 0 and fac.population / total_cap > 0.7:
            return True
    return False


@register("faction_in_low_habitability_region")
def _low_habitability(state: WorldState, faction_id: str | None) -> bool:
    for fac in state.factions.values():
        if faction_id and fac.id != faction_id:
            continue
        for reg_id in fac.regions:
            region = state.regions.get(reg_id)
            if region and region.habitability < 0.4:
                return True
    return False


@register("any_trade_route_active")
def _trade_route(state: WorldState, faction_id: str | None) -> bool:
    return state.trade_routes_active


@register("region_with_mountains_or_ancient")
def _mountains_or_ancient(state: WorldState, faction_id: str | None) -> bool:
    for region in state.regions.values():
        terrain = region.terrain.lower()
        if "mountain" in terrain or "ancient" in terrain:
            return True
    return False


@register("any_faction_has_advanced_arcane")
def _advanced_arcane(state: WorldState, faction_id: str | None) -> bool:
    for fac in state.factions.values():
        for tech_id in fac.unlocked_techs:
            tech_name = tech_id.lower()
            if "advanced" in tech_name or "haute" in tech_name:
                return True
            # Also check tech name from config
            for t in state.config["tech_tree"]["nodes"]:
                if t["id"] == tech_id and ("advanced" in t["name"].lower() or "haute" in t["name"].lower()):
                    return True
    return False
