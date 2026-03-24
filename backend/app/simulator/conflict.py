"""Conflict resolution between two factions."""

import random

from app.simulator.types import WorldState, FactionState


def resolve_conflict(
    attacker: FactionState,
    defender: FactionState,
    state: WorldState,
    rng: random.Random,
) -> dict:
    """Resolve a conflict between two factions. Returns outcome dict."""

    attack_score = _calc_attack_score(attacker, state, rng)
    defense_score = _calc_defense_score(defender, state, rng)

    if attack_score > defense_score:
        winner, loser = attacker, defender
    else:
        winner, loser = defender, attacker

    outcome = {
        "winner": winner.id,
        "loser": loser.id,
        "population_losses": {},
    }

    # Population losses
    winner_loss = int(winner.population * 0.05)
    loser_loss = int(loser.population * 0.15)
    winner.population = max(1, winner.population - winner_loss)
    loser.population = max(1, loser.population - loser_loss)
    outcome["population_losses"] = {winner.id: winner_loss, loser.id: loser_loss}

    # Territory change: loser loses a region adjacent to winner if possible
    territory_changed = _try_territory_transfer(winner, loser, state)
    if territory_changed:
        outcome["territory_changed"] = territory_changed

    # Cohesion impact on loser
    loser.attributes.apply_modifier("cohesion", -0.1)

    return outcome


def _calc_attack_score(faction: FactionState, state: WorldState, rng: random.Random) -> float:
    base = faction.attributes.aggressiveness * faction.population

    # Tech attack bonus
    tech_bonus = 0.0
    for tech_id in faction.unlocked_techs:
        tech = _find_tech(state.config, tech_id)
        if tech:
            tech_bonus += tech["effects"].get("attack_bonus", 0.0)

    score = base * (1.0 + tech_bonus)

    # Random factor ±20%
    score *= 1.0 + rng.uniform(-0.2, 0.2)

    return score


def _calc_defense_score(faction: FactionState, state: WorldState, rng: random.Random) -> float:
    base = faction.attributes.cohesion * faction.population

    # Tech defense bonus
    tech_bonus = 0.0
    for tech_id in faction.unlocked_techs:
        tech = _find_tech(state.config, tech_id)
        if tech:
            tech_bonus += tech["effects"].get("defense_bonus", 0.0)

    # Terrain bonus: mountainous/arid regions give +20% defense
    terrain_bonus = 0.0
    for reg_id in faction.regions:
        region = state.regions.get(reg_id)
        if region:
            terrain = region.terrain.lower()
            if "mountain" in terrain:
                terrain_bonus += 0.2
            elif "forest" in terrain:
                terrain_bonus += 0.1

    score = base * (1.0 + tech_bonus + terrain_bonus)

    # Random factor ±20%
    score *= 1.0 + rng.uniform(-0.2, 0.2)

    return score


def _try_territory_transfer(winner: FactionState, loser: FactionState, state: WorldState) -> str | None:
    """Transfer a region from loser to winner if they share a border. Returns region ID or None."""
    if len(loser.regions) <= 1:
        return None  # Can't lose last region

    winner_regions = set(winner.regions)

    for reg_id in list(loser.regions):
        region = state.regions.get(reg_id)
        if not region:
            continue
        # Check if this region is adjacent to any winner region
        for conn in region.connections:
            if conn["target"] in winner_regions:
                loser.regions.remove(reg_id)
                winner.regions.append(reg_id)
                return reg_id

    return None


def _find_tech(config: dict, tech_id: str) -> dict | None:
    for tech in config["tech_tree"]["nodes"]:
        if tech["id"] == tech_id:
            return tech
    return None
