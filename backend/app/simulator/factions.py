"""Faction logic: population growth, attribute updates from resources and characters."""

from app.simulator.types import WorldState


def update_factions(state: WorldState):
    """Update all factions for the current tick: population growth + resource/character effects."""
    for faction in state.factions.values():
        _grow_population(faction, state)
        _apply_resource_effects(faction, state)
        _apply_character_effects(faction, state)


def _grow_population(faction, state: WorldState):
    """Natural growth: population * fertility * 0.02, capped by max_population of owned regions."""
    total_capacity = sum(
        state.regions[reg_id].max_population
        for reg_id in faction.regions
        if reg_id in state.regions
    )

    # Apply tech modifiers to capacity
    for tech_id in faction.unlocked_techs:
        tech = _find_tech(state.config, tech_id)
        if tech:
            modifier = tech["effects"].get("max_population_modifier", 1.0)
            if modifier != 1.0:
                total_capacity = int(total_capacity * modifier)

    growth = int(faction.population * faction.attributes.fertility * 0.02)
    faction.population = min(faction.population + growth, total_capacity)


def _apply_resource_effects(faction, state: WorldState):
    """Apply resource effects to faction attributes."""
    resource_map = {r["id"]: r for r in state.config["resources"]}

    for reg_id in faction.regions:
        region = state.regions.get(reg_id)
        if not region:
            continue
        for res_id in region.resources:
            resource = resource_map.get(res_id)
            if not resource:
                continue
            for attr, bonus in resource["effects"].items():
                # Resources apply a small fraction per tick (not full bonus each tick)
                faction.attributes.apply_modifier(attr, bonus * 0.01)


def _apply_character_effects(faction, state: WorldState):
    """Apply active character modifiers to faction attributes."""
    for char in state.active_characters:
        if char.faction_id == faction.id:
            for attr, mod in char.attribute_modifiers.items():
                faction.attributes.apply_modifier(attr, mod * 0.01 * char.impact)


def _find_tech(config: dict, tech_id: str) -> dict | None:
    for tech in config["tech_tree"]["nodes"]:
        if tech["id"] == tech_id:
            return tech
    return None
