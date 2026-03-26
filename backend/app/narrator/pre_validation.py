# app/narrator/pre_validation.py
"""Programmatic pre-validation — catches and fixes obvious coherence issues without LLM."""

import logging

logger = logging.getLogger("worldforge.narrator.pre_validation")


def pre_validate(narrative_blocks: dict, config: dict) -> int:
    """Run deterministic coherence checks and auto-fix obvious issues.

    Modifies narrative_blocks in place.

    Returns:
        Number of fixes applied.
    """
    fixes = 0
    fixes += _fix_era_overlaps(narrative_blocks)
    fixes += _fix_character_dates(narrative_blocks)
    fixes += _fix_event_era_alignment(narrative_blocks)
    fixes += _normalize_faction_references(narrative_blocks, config)

    if fixes:
        logger.info("Pre-validation applied %d auto-fixes", fixes)
    return fixes


def _fix_era_overlaps(narrative_blocks: dict) -> int:
    """Fix overlapping era boundaries by making them contiguous."""
    eras = narrative_blocks.get("eras", [])
    if len(eras) < 2:
        return 0

    # Filter to valid dicts and sort by start_year
    valid_eras = [e for e in eras if isinstance(e, dict) and isinstance(e.get("start_year"), (int, float))]
    if len(valid_eras) < 2:
        return 0

    valid_eras.sort(key=lambda e: e["start_year"])
    fixes = 0

    for i in range(len(valid_eras) - 1):
        current = valid_eras[i]
        next_era = valid_eras[i + 1]

        current_end = current.get("end_year")
        next_start = next_era.get("start_year")

        if isinstance(current_end, (int, float)) and isinstance(next_start, (int, float)):
            # Fix overlap: current era ends after next era starts
            if current_end >= next_start:
                current["end_year"] = next_start - 1
                fixes += 1
                logger.info(
                    "Fixed era overlap: '%s' end_year %s -> %s (before '%s' start)",
                    current.get("name", "?"), current_end, next_start - 1, next_era.get("name", "?"),
                )

    return fixes


def _fix_character_dates(narrative_blocks: dict) -> int:
    """Ensure character birth/death years fall within era boundaries."""
    eras = narrative_blocks.get("eras", [])
    if not eras:
        return 0

    # Build era timeline
    era_ranges = []
    for era in eras:
        if not isinstance(era, dict):
            continue
        era_ranges.append((
            era.get("start_year", 0),
            era.get("end_year", float("inf")),
            era.get("name", "?"),
        ))
    era_ranges.sort(key=lambda x: x[0])

    if not era_ranges:
        return 0

    world_start = era_ranges[0][0]
    world_end = era_ranges[-1][1]
    fixes = 0

    characters = narrative_blocks.get("characters", [])
    for char in characters:
        if not isinstance(char, dict):
            continue

        birth = char.get("birth_year")
        death = char.get("death_year")

        # Clamp birth year to world timeline
        if isinstance(birth, (int, float)):
            if birth < world_start:
                char["birth_year"] = world_start
                fixes += 1
            elif birth > world_end:
                char["birth_year"] = world_end - 10
                fixes += 1

        # Ensure death > birth
        if isinstance(birth, (int, float)) and isinstance(death, (int, float)):
            if death <= birth:
                char["death_year"] = birth + 20
                fixes += 1

    return fixes


def _fix_event_era_alignment(narrative_blocks: dict) -> int:
    """Ensure event years match their stated era."""
    eras = narrative_blocks.get("eras", [])
    if not eras:
        return 0

    # Build era lookup by name
    era_by_name: dict[str, dict] = {}
    for era in eras:
        if isinstance(era, dict) and era.get("name"):
            era_by_name[era["name"]] = era
            # Also index by lowercase for fuzzy matching
            era_by_name[era["name"].lower()] = era

    fixes = 0
    events = narrative_blocks.get("events", [])
    for evt in events:
        if not isinstance(evt, dict):
            continue

        evt_era = evt.get("era", "")
        evt_year = evt.get("year")

        if not evt_era or not isinstance(evt_year, (int, float)):
            continue

        # Find the matching era
        era = era_by_name.get(evt_era) or era_by_name.get(evt_era.lower())
        if not era:
            continue

        start = era.get("start_year", 0)
        end = era.get("end_year", float("inf"))

        # Clamp year to era bounds
        if evt_year < start:
            evt["year"] = start
            fixes += 1
        elif evt_year > end:
            evt["year"] = end
            fixes += 1

    return fixes


def _normalize_faction_references(narrative_blocks: dict, config: dict) -> int:
    """Replace faction references that are close matches to known factions."""
    # Build known faction names
    known_factions = set()
    for fac in config.get("factions", []):
        name = fac.get("name", "")
        if name:
            known_factions.add(name)

    # Also include factions from narrative blocks
    for fac in narrative_blocks.get("factions", []):
        if isinstance(fac, dict):
            name = fac.get("name", "")
            if name:
                known_factions.add(name)

    if not known_factions:
        return 0

    # Build lowercase lookup for fuzzy matching
    lower_to_original = {name.lower(): name for name in known_factions}

    fixes = 0

    # Check events
    for evt in narrative_blocks.get("events", []):
        if not isinstance(evt, dict):
            continue
        factions = evt.get("involved_factions", [])
        if not isinstance(factions, list):
            continue
        new_factions = []
        for fac_ref in factions:
            if not isinstance(fac_ref, str):
                new_factions.append(fac_ref)
                continue
            if fac_ref in known_factions:
                new_factions.append(fac_ref)
            elif fac_ref.lower() in lower_to_original:
                new_factions.append(lower_to_original[fac_ref.lower()])
                fixes += 1
            else:
                # Keep as-is — might be a new faction introduced narratively
                new_factions.append(fac_ref)
        evt["involved_factions"] = new_factions

    # Check characters
    for char in narrative_blocks.get("characters", []):
        if not isinstance(char, dict):
            continue
        fac_ref = char.get("faction", "")
        if isinstance(fac_ref, str) and fac_ref and fac_ref not in known_factions:
            if fac_ref.lower() in lower_to_original:
                char["faction"] = lower_to_original[fac_ref.lower()]
                fixes += 1

    return fixes
