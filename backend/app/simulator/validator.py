# app/simulator/validator.py
"""Post-simulation validator — checks timeline invariants."""

import logging

logger = logging.getLogger("worldforge.simulator.validator")


def validate_timeline(timeline: dict, config: dict) -> list[str]:
    """Validate timeline invariants. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Build tech prerequisite map
    tech_nodes = {t["id"]: t for t in config.get("tech_tree", {}).get("nodes", [])}

    # Track character lifecycle
    alive_characters: dict[str, int] = {}   # placeholder -> spawn year
    dead_characters: dict[str, int] = {}    # placeholder -> retire year

    # Track faction unlocked techs
    faction_techs: dict[str, set[str]] = {f["id"]: set() for f in config.get("factions", [])}

    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)

        # Character lifecycle
        for ce in tick.get("character_events", []):
            placeholder = ce.get("name_placeholder", "")
            if ce.get("type") == "spawn":
                alive_characters[placeholder] = year
            elif ce.get("type") == "retire":
                if placeholder in alive_characters:
                    dead_characters[placeholder] = year
                    del alive_characters[placeholder]

        # Check dead characters in events
        for evt in tick.get("events", []):
            for char in evt.get("involved_characters", []):
                if char in dead_characters:
                    errors.append(
                        f"Année {year}: personnage '{char}' mort en {dead_characters[char]} "
                        f"impliqué dans l'événement '{evt.get('event_id', '?')}'"
                    )

        # Tech prerequisite validation
        for tu in tick.get("tech_unlocks", []):
            fac_id = tu.get("faction_id", "")
            tech_id = tu.get("tech_id", "")
            tech_def = tech_nodes.get(tech_id)
            if tech_def:
                for prereq in tech_def.get("prerequisites", []):
                    if prereq not in faction_techs.get(fac_id, set()):
                        errors.append(
                            f"Année {year}: faction '{fac_id}' débloque '{tech_id}' "
                            f"sans prérequis '{prereq}'"
                        )
            faction_techs.setdefault(fac_id, set()).add(tech_id)

        # World state checks
        ws = tick.get("world_state", {})
        for fac in ws.get("factions", []):
            fac_id = fac.get("id", "?")
            pop = fac.get("population", 0)
            if pop < 0:
                errors.append(f"Année {year}: faction '{fac_id}' a une population négative ({pop})")

    if errors:
        logger.warning("Timeline validation: %d errors found", len(errors))
    else:
        logger.info("Timeline validation: OK")

    return errors
