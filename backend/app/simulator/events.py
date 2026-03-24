"""Event evaluation, triggering, and cascade processing."""

import random

from app.simulator.types import WorldState, EventRecord, FactionState, Attributes, Relation
from app.simulator.preconditions import check_precondition
from app.simulator.conflict import resolve_conflict
from app.simulator.relations import update_relation, get_rivalry_intensity


def process_events(state: WorldState, rng: random.Random) -> list[EventRecord]:
    """Evaluate all events in the pool, trigger those that fire, return records."""
    records = []
    chaos_level = state.config["meta"]["chaos_level"]

    for event_cfg in state.config["event_pool"]:
        triggered = _try_trigger_event(event_cfg, state, rng, chaos_level)
        if triggered:
            records.append(triggered)

    # Process cascades from black swans
    cascade_records = []
    for record in records:
        event_cfg = _find_event(state.config, record.event_id)
        if event_cfg and event_cfg.get("cascade"):
            for cascade in event_cfg["cascade"]:
                if rng.random() < cascade["probability"]:
                    cascade_cfg = _find_event(state.config, cascade["event"])
                    if cascade_cfg:
                        cascade_result = _apply_event(cascade_cfg, state, rng, is_cascade=True)
                        if cascade_result:
                            cascade_records.append(cascade_result)

    records.extend(cascade_records)
    return records


def _try_trigger_event(
    event_cfg: dict,
    state: WorldState,
    rng: random.Random,
    chaos_level: float,
) -> EventRecord | None:
    """Evaluate and possibly trigger a single event."""

    # Check preconditions
    requires = event_cfg["preconditions"]["requires"]
    if not check_precondition(requires, state):
        return None

    # Check min_attribute if specified
    min_attr = event_cfg["preconditions"].get("min_attribute", {})
    if min_attr:
        if not _any_faction_meets_min_attr(state, min_attr):
            return None

    # Calculate adjusted probability
    prob = event_cfg["base_probability"]

    # Apply modifiers
    for modifier in event_cfg.get("modifiers", []):
        if _check_modifier_condition(modifier["condition"], state):
            prob += modifier["probability_bonus"]

    # Black swan: multiply by chaos_level
    if event_cfg["is_black_swan"]:
        prob *= chaos_level

    # Roll
    if rng.random() >= prob:
        return None

    return _apply_event(event_cfg, state, rng)


def _apply_event(
    event_cfg: dict,
    state: WorldState,
    rng: random.Random,
    is_cascade: bool = False,
) -> EventRecord | None:
    """Apply an event's consequences and return an EventRecord."""
    category = event_cfg["category"]
    consequences = event_cfg["consequences"]

    if category == "conflict":
        return _apply_conflict(event_cfg, state, rng)
    elif category == "diplomacy":
        return _apply_diplomacy(event_cfg, state, rng)
    elif category == "internal":
        return _apply_internal(event_cfg, state, rng)
    elif category == "catastrophe":
        return _apply_catastrophe(event_cfg, state, rng)
    elif category == "migration":
        return _apply_migration(event_cfg, state, rng)
    elif category == "discovery":
        return _apply_discovery(event_cfg, state, rng)

    return None


def _apply_conflict(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    pairs = state.get_adjacent_faction_pairs()
    if not pairs:
        return None

    # Pick the pair with highest rivalry
    best_pair = max(pairs, key=lambda p: get_rivalry_intensity(state, p[0], p[1]))
    attacker_id, defender_id = best_pair

    attacker = state.factions[attacker_id]
    defender = state.factions[defender_id]

    # Faction with higher aggressiveness attacks
    if defender.attributes.aggressiveness > attacker.attributes.aggressiveness:
        attacker, defender = defender, attacker

    outcome = resolve_conflict(attacker, defender, state, rng)
    update_relation(state, attacker.id, defender.id, "conflict")

    regions = list(set(attacker.regions + defender.regions))

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=[attacker.id, defender.id],
        involved_regions=regions,
        outcome=outcome,
    )


def _apply_diplomacy(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    pairs = state.get_adjacent_faction_pairs()
    if not pairs:
        return None

    # Pick pair with lowest rivalry
    best_pair = min(pairs, key=lambda p: get_rivalry_intensity(state, p[0], p[1]))
    fac_a_id, fac_b_id = best_pair
    fac_a = state.factions[fac_a_id]
    fac_b = state.factions[fac_b_id]

    # Apply consequences to both
    both_effects = event_cfg["consequences"].get("both", {})
    for attr, val in both_effects.items():
        fac_a.attributes.apply_modifier(attr, val)
        fac_b.attributes.apply_modifier(attr, val)

    update_relation(state, fac_a_id, fac_b_id, "diplomacy")

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=[fac_a_id, fac_b_id],
        involved_regions=[],
        outcome={"type": "diplomacy", "effects_applied": both_effects},
    )


def _apply_internal(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    # Find applicable faction
    candidates = list(state.factions.values())
    requires = event_cfg["preconditions"]["requires"]

    if "monarchy" in requires or "chieftain" in requires:
        candidates = [f for f in candidates if _is_monarchy_or_chieftain(f)]
    elif "theocracy" in requires or "council" in requires:
        candidates = [f for f in candidates if _is_theocracy_or_council(f)]

    if not candidates:
        return None

    faction = rng.choice(candidates)
    effects = event_cfg["consequences"].get("faction", {})

    for attr, val in effects.items():
        if attr == "civil_war_chance":
            continue
        if attr == "faction_split_chance":
            if rng.random() < val:
                _split_faction(faction, state, rng)
            continue
        faction.attributes.apply_modifier(attr, val)

    # Civil war chance
    civil_war_chance = effects.get("civil_war_chance", 0)
    if civil_war_chance > 0 and rng.random() < civil_war_chance:
        faction.attributes.apply_modifier("cohesion", -0.15)

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=[faction.id],
        involved_regions=list(faction.regions),
        outcome={"faction": faction.id, "effects_applied": effects},
    )


def _apply_catastrophe(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    consequences = event_cfg["consequences"]
    involved_factions = []
    involved_regions = []

    # Global effects
    if "global" in consequences:
        for attr, val in consequences["global"].items():
            if attr == "habitability_all_regions":
                for region in state.regions.values():
                    region.habitability = max(0.0, region.habitability + val)
                    involved_regions.append(region.id)
            elif attr.startswith("all_"):
                real_attr = attr[4:]  # strip "all_"
                for fac in state.factions.values():
                    fac.attributes.apply_modifier(real_attr, val)
                    involved_factions.append(fac.id)

    # Region effects
    if "region" in consequences:
        # Pick a region matching the precondition
        matching = [r for r in state.regions.values()
                    if "mountain" in r.terrain.lower() or "ancient" in r.terrain.lower()]
        if matching:
            region = rng.choice(matching)
            involved_regions.append(region.id)
            for attr, val in consequences["region"].items():
                if attr == "habitability":
                    region.habitability = max(0.0, region.habitability + val)
                elif attr == "population_loss":
                    for fac in state.factions.values():
                        if region.id in fac.regions:
                            loss = int(fac.population * val)
                            fac.population = max(1, fac.population - loss)
                            involved_factions.append(fac.id)

    # All factions in region effects
    if "all_factions_in_region" in consequences and involved_regions:
        for fac in state.factions.values():
            if any(r in fac.regions for r in involved_regions):
                for attr, val in consequences["all_factions_in_region"].items():
                    fac.attributes.apply_modifier(attr, val)
                if fac.id not in involved_factions:
                    involved_factions.append(fac.id)

    # Connected factions effects
    if "all_connected_factions" in consequences:
        for fac in state.factions.values():
            effects = consequences["all_connected_factions"]
            pop_loss = effects.get("population_loss", 0)
            if pop_loss:
                fac.population = max(1, fac.population - int(fac.population * pop_loss))
            for attr, val in effects.items():
                if attr != "population_loss":
                    fac.attributes.apply_modifier(attr, val)
            involved_factions.append(fac.id)

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=list(set(involved_factions)),
        involved_regions=list(set(involved_regions)),
        outcome={"type": "catastrophe"},
    )


def _apply_migration(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    # Find faction in low habitability region
    candidates = []
    for fac in state.factions.values():
        for reg_id in fac.regions:
            region = state.regions.get(reg_id)
            if region and region.habitability < 0.5:
                candidates.append((fac, reg_id))

    if not candidates:
        return None

    faction, origin_reg = rng.choice(candidates)
    origin_region = state.regions[origin_reg]

    # Find destination: connected region with better habitability
    destinations = []
    for conn in origin_region.connections:
        dest = state.regions.get(conn["target"])
        if dest and dest.habitability > origin_region.habitability:
            destinations.append(dest)

    if not destinations:
        return None

    dest_region = rng.choice(destinations)
    pop_moved = int(faction.population * 0.1)
    faction.population = max(1, faction.population - pop_moved)

    # Add population to destination faction(s) or expand
    dest_factions = [f for f in state.factions.values() if dest_region.id in f.regions]
    if dest_factions:
        dest_fac = dest_factions[0]
        dest_fac.population += pop_moved
        dest_fac.attributes.apply_modifier("cohesion", -0.05)
    else:
        # Faction expands to new region
        faction.regions.append(dest_region.id)
        faction.population += pop_moved

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=[faction.id] + [f.id for f in dest_factions],
        involved_regions=[origin_reg, dest_region.id],
        outcome={"origin": origin_reg, "destination": dest_region.id, "population_moved": pop_moved},
    )


def _apply_discovery(event_cfg: dict, state: WorldState, rng: random.Random) -> EventRecord | None:
    # Find faction with enough power_affinity
    candidates = [f for f in state.factions.values() if f.attributes.power_affinity > 0.3]
    if not candidates:
        return None

    faction = rng.choice(candidates)
    effects = event_cfg["consequences"].get("faction", {})

    # Unlock random tech
    if effects.get("unlock_random_tech"):
        tech_map = {t["id"]: t for t in state.config["tech_tree"]["nodes"]}
        unlocked = set(faction.unlocked_techs)
        available = [
            t_id for t_id, t in tech_map.items()
            if t_id not in unlocked and all(p in unlocked for p in t["prerequisites"])
        ]
        if available:
            new_tech = rng.choice(available)
            faction.unlocked_techs.append(new_tech)

    for attr, val in effects.items():
        if attr == "unlock_random_tech":
            continue
        faction.attributes.apply_modifier(attr, val)

    return EventRecord(
        event_id=event_cfg["id"],
        involved_factions=[faction.id],
        involved_regions=[],
        outcome={"faction": faction.id, "type": "discovery"},
    )


def _split_faction(faction: FactionState, state: WorldState, rng: random.Random):
    """Split a faction into two. Section 5.7 of specs."""
    if len(faction.regions) < 2 and faction.population < 1000:
        return

    new_id = f"{faction.id}_split_{state.year}"
    new_name = f"{faction.name} (Scission)"

    # Population split 60/40
    new_pop = int(faction.population * 0.4)
    faction.population -= new_pop

    # New faction gets a region if possible
    new_regions = []
    if len(faction.regions) > 1:
        new_regions = [faction.regions.pop()]
    else:
        new_regions = list(faction.regions)  # share the region

    # Mutate attributes ±0.1
    new_attrs = Attributes.from_dict(faction.attributes.to_dict())
    for attr in ("aggressiveness", "cohesion", "expansionism", "power_affinity", "fertility", "adaptability"):
        mutation = rng.uniform(-0.1, 0.1)
        new_attrs.apply_modifier(attr, mutation)

    new_faction = FactionState(
        id=new_id,
        name=new_name,
        governance=faction.governance,
        avg_lifespan=faction.avg_lifespan,
        cultural_traits=list(faction.cultural_traits),
        attributes=new_attrs,
        population=new_pop,
        regions=new_regions,
        unlocked_techs=list(faction.unlocked_techs),
    )

    state.factions[new_id] = new_faction

    # Add rivalry relation
    state.relations.append(Relation(
        faction_a=faction.id,
        faction_b=new_id,
        type="rivalry",
        intensity=0.5,
    ))


def _any_faction_meets_min_attr(state: WorldState, min_attr: dict) -> bool:
    for fac in state.factions.values():
        meets = True
        for attr, threshold in min_attr.items():
            if getattr(fac.attributes, attr, 0) < threshold:
                meets = False
                break
        if meets:
            return True
    return False


def _check_modifier_condition(condition: str, state: WorldState) -> bool:
    """Simple condition checker for event modifiers."""
    cond = condition.lower()

    if "resource_competition" in cond:
        # Two factions sharing resources in connected regions
        return len(state.get_adjacent_faction_pairs()) > 1

    if "shared_resource_need" in cond:
        return len(state.get_adjacent_faction_pairs()) > 0

    if "both_low_aggressiveness" in cond:
        low = [f for f in state.factions.values() if f.attributes.aggressiveness < 0.4]
        return len(low) >= 2

    if "attacker_aggressiveness_above" in cond:
        return any(f.attributes.aggressiveness > 0.7 for f in state.factions.values())

    if "defender_cohesion_below" in cond:
        return any(f.attributes.cohesion < 0.3 for f in state.factions.values())

    if "cohesion_below" in cond:
        return any(f.attributes.cohesion < 0.4 for f in state.factions.values())

    if "leader_death" in cond:
        return False  # Only triggered by character system

    if "no_medicine_tech" in cond:
        return any(
            "medicine" not in " ".join(f.unlocked_techs).lower()
            for f in state.factions.values()
        )

    if "trade_route_active" in cond:
        return state.trade_routes_active

    if "famine_active" in cond:
        return any(f.attributes.fertility < 0.2 for f in state.factions.values())

    if "war_lost_recently" in cond:
        return False  # Would need event history tracking

    if "power_affinity_above" in cond:
        return any(f.attributes.power_affinity > 0.6 for f in state.factions.values())

    if "multi_region_faction" in cond:
        return any(len(f.regions) > 1 for f in state.factions.values())

    if "controls_rare_resource" in cond:
        rare = {r["id"] for r in state.config["resources"] if r["rarity"] > 0.6}
        for fac in state.factions.values():
            for reg_id in fac.regions:
                region = state.regions.get(reg_id)
                if region and any(r in rare for r in region.resources):
                    return True
        return False

    if "high_magic_activity" in cond:
        return any(f.attributes.power_affinity > 0.7 for f in state.factions.values())

    if "high_population_density" in cond:
        for fac in state.factions.values():
            total_cap = sum(state.regions[r].max_population for r in fac.regions if r in state.regions)
            if total_cap > 0 and fac.population / total_cap > 0.8:
                return True
        return False

    if "multiple_factions_with_magic" in cond:
        magic_facs = [f for f in state.factions.values() if f.attributes.power_affinity > 0.5]
        return len(magic_facs) >= 2

    if "common_threat_active" in cond:
        return any(e["is_black_swan"] for e in state.config["event_pool"])

    # Unknown condition — permissive
    return False


def _is_monarchy_or_chieftain(fac: FactionState) -> bool:
    gov = fac.governance.lower()
    return any(k in gov for k in ("monarchy", "chieftain", "tribal", "king", "queen"))


def _is_theocracy_or_council(fac: FactionState) -> bool:
    gov = fac.governance.lower()
    return any(k in gov for k in ("theocracy", "council", "conseil"))


def _find_event(config: dict, event_id: str) -> dict | None:
    for e in config["event_pool"]:
        if e["id"] == event_id:
            return e
    return None
