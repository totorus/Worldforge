"""Character spawn and lifecycle management."""

import random

from app.simulator.types import WorldState, Character, CharacterEvent


def process_characters(state: WorldState, rng: random.Random) -> list[CharacterEvent]:
    """Spawn new characters and retire expired ones. Returns events."""
    events = []

    # Retire expired characters
    expired = [c for c in state.active_characters if state.year >= c.end_year]
    for char in expired:
        state.active_characters.remove(char)
        events.append(CharacterEvent(
            type="retire",
            faction_id=char.faction_id,
            role=char.role_id,
            name_placeholder=char.name_placeholder,
        ))

    # Spawn new characters
    spawn_prob = state.config["character_rules"]["spawn_probability_per_tick"]
    roles = state.config["character_rules"]["roles"]

    for faction in state.factions.values():
        if rng.random() >= spawn_prob:
            continue

        # Pick a role, weighted by cultural traits
        role = _pick_role(faction, roles, rng)
        if not role:
            continue

        # Determine impact and duration
        impact = rng.uniform(role["impact_range"][0], role["impact_range"][1])
        duration = rng.randint(role["duration_ticks"][0], role["duration_ticks"][1])

        placeholder = f"{role['id'].upper()}_{faction.id.upper()}_Y{state.year}"

        char = Character(
            id=f"char_{faction.id}_{state.year}_{role['id']}",
            faction_id=faction.id,
            role_id=role["id"],
            name_placeholder=placeholder,
            spawn_year=state.year,
            duration_ticks=duration,
            impact=impact,
            attribute_modifiers=dict(role["attribute_modifiers"]),
        )

        state.active_characters.append(char)
        events.append(CharacterEvent(
            type="spawn",
            faction_id=faction.id,
            role=role["id"],
            name_placeholder=placeholder,
        ))

    return events


def _pick_role(faction, roles: list[dict], rng: random.Random) -> dict | None:
    """Pick a role, adjusting probability based on cultural traits."""
    weights = []
    for role in roles:
        weight = 1.0

        # Honor-bound factions spawn fewer traitors
        if role["id"] == "role_traitor" and "honor_bound" in faction.cultural_traits:
            weight *= 0.5

        # Scholarly factions spawn more scholars
        if role["id"] == "role_scholar" and "scholarly" in faction.cultural_traits:
            weight *= 2.0

        # Aggressive factions spawn more heroes
        if role["id"] == "role_hero" and faction.attributes.aggressiveness > 0.6:
            weight *= 1.5

        weights.append(weight)

    total = sum(weights)
    if total == 0:
        return None

    r = rng.random() * total
    cumulative = 0.0
    for role, weight in zip(roles, weights):
        cumulative += weight
        if r <= cumulative:
            return role

    return roles[-1]
