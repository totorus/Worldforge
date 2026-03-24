"""Main simulation engine — tick-by-tick world simulation."""

import hashlib
import json
import random
import uuid

from app.simulator.types import (
    WorldState, FactionState, RegionState, Attributes, Relation, TickResult,
)
from app.simulator.factions import update_factions
from app.simulator.tech import process_tech_unlocks
from app.simulator.events import process_events
from app.simulator.characters import process_characters


def run_simulation(config: dict, start_state: dict | None = None) -> dict:
    """Run a full simulation from config. Returns timeline JSON.

    Args:
        config: Validated world configuration dict.
        start_state: Optional existing world_state to resume from (for prolongation).

    Returns:
        Timeline dict with world_id, config_hash, seed, and ticks array.
    """
    seed = config["meta"]["seed"]
    rng = random.Random(seed)
    world_id = str(uuid.uuid4())

    state = _init_world_state(config) if start_state is None else _restore_world_state(config, start_state)

    simulation_years = config["meta"]["simulation_years"]
    tick_duration = config["meta"]["tick_duration_years"]
    total_ticks = simulation_years // tick_duration

    ticks = []

    for tick_num in range(total_ticks):
        state.year = (tick_num + 1) * tick_duration
        tick_result = _run_tick(state, rng)
        ticks.append(tick_result.to_dict())

    return {
        "world_id": world_id,
        "config_hash": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "seed": seed,
        "ticks": ticks,
    }


def _run_tick(state: WorldState, rng: random.Random) -> TickResult:
    """Execute one tick of the simulation. Follows the loop from specs section 5.2."""
    tick = TickResult(year=state.year)

    # 1. Update faction attributes (population growth, resource effects, character effects)
    update_factions(state)

    # 2. Tech unlocks
    tech_unlocks = process_tech_unlocks(state, rng)
    tick.tech_unlocks = tech_unlocks

    # 3-5. Evaluate and apply events (includes conflict resolution and cascades)
    event_records = process_events(state, rng)
    tick.events = event_records

    # 6. Character management (spawn and retire)
    char_events = process_characters(state, rng)
    tick.character_events = char_events

    # 7. Snapshot world state
    tick.world_state = state.snapshot()

    return tick


def _init_world_state(config: dict) -> WorldState:
    """Initialize world state from config's initial_state."""
    state = WorldState(config=config)

    # Build regions
    for reg_cfg in config["geography"]["regions"]:
        state.regions[reg_cfg["id"]] = RegionState(
            id=reg_cfg["id"],
            name=reg_cfg["name"],
            terrain=reg_cfg["terrain"],
            habitability=reg_cfg["habitability"],
            max_population=reg_cfg["max_population"],
            resources=list(reg_cfg["resources"]),
            connections=list(reg_cfg["connections"]),
        )

    # Build factions from initial state + faction definitions
    faction_defs = {f["id"]: f for f in config["factions"]}

    for fs_cfg in config["initial_state"]["faction_states"]:
        fac_def = faction_defs[fs_cfg["faction_id"]]
        state.factions[fs_cfg["faction_id"]] = FactionState(
            id=fs_cfg["faction_id"],
            name=fac_def["name"],
            governance=fac_def["governance"],
            avg_lifespan=fac_def["avg_lifespan"],
            cultural_traits=list(fac_def["cultural_traits"]),
            attributes=Attributes.from_dict(fac_def["attributes"]),
            population=fs_cfg["starting_population"],
            regions=list(fs_cfg["starting_regions"]),
            unlocked_techs=list(fs_cfg["unlocked_techs"]),
        )

    # Build initial relations
    for rel_cfg in config["initial_state"]["initial_relations"]:
        state.relations.append(Relation(
            faction_a=rel_cfg["faction_a"],
            faction_b=rel_cfg["faction_b"],
            type=rel_cfg["type"],
            intensity=rel_cfg["intensity"],
        ))

    return state


def _restore_world_state(config: dict, world_state_snapshot: dict) -> WorldState:
    """Restore world state from a snapshot (for prolongation)."""
    state = WorldState(config=config)

    # Restore regions from config (they don't change much)
    for reg_cfg in config["geography"]["regions"]:
        state.regions[reg_cfg["id"]] = RegionState(
            id=reg_cfg["id"],
            name=reg_cfg["name"],
            terrain=reg_cfg["terrain"],
            habitability=reg_cfg["habitability"],
            max_population=reg_cfg["max_population"],
            resources=list(reg_cfg["resources"]),
            connections=list(reg_cfg["connections"]),
        )

    # Restore factions from snapshot
    faction_defs = {f["id"]: f for f in config["factions"]}

    for fac_snap in world_state_snapshot["factions"]:
        fac_def = faction_defs.get(fac_snap["id"])
        governance = fac_def["governance"] if fac_def else "unknown"
        avg_lifespan = fac_def["avg_lifespan"] if fac_def else 50
        cultural_traits = fac_def["cultural_traits"] if fac_def else []

        state.factions[fac_snap["id"]] = FactionState(
            id=fac_snap["id"],
            name=fac_snap.get("name", fac_snap["id"]),
            governance=governance,
            avg_lifespan=avg_lifespan,
            cultural_traits=cultural_traits,
            attributes=Attributes.from_dict(fac_snap["attributes"]),
            population=fac_snap["population"],
            regions=list(fac_snap["regions"]),
            unlocked_techs=list(fac_snap.get("unlocked_techs", [])),
        )

    # Restore relations from snapshot
    for rel_snap in world_state_snapshot.get("relations", []):
        state.relations.append(Relation(
            faction_a=rel_snap["faction_a"],
            faction_b=rel_snap["faction_b"],
            type=rel_snap["type"],
            intensity=rel_snap["intensity"],
        ))

    return state
