"""Narration pipeline orchestrator — runs all narrative enrichment steps sequentially."""

import logging

from app.narrator.eras import split_into_eras
from app.narrator.naming import generate_names
from app.narrator.sheets import generate_faction_sheet, generate_region_sheet
from app.narrator.events_narrator import narrate_events
from app.narrator.characters_narrator import generate_biographies, _extract_characters
from app.narrator.legends import generate_legends
from app.narrator.coherence import check_coherence
from app.narrator.entity_extraction import run_entity_extraction
from app.narrator.coherence_fix import fix_coherence_issues

logger = logging.getLogger("worldforge.narrator.pipeline")

# Ordered list of all narration steps
ALL_STEPS = [
    "era_splitting",
    "naming",
    "faction_sheets",
    "region_sheets",
    "event_narratives",
    "character_bios",
    "legends",
    "entity_extraction",
    "coherence_check",
]


async def run_narration(config: dict, timeline: dict) -> dict:
    """Run the full narration pipeline on a simulated world.

    Calls each step sequentially:
        era_splitting -> naming -> faction_sheets -> region_sheets ->
        event_narratives -> character_bios -> legends -> coherence_check

    Args:
        config: Validated world configuration dict.
        timeline: Simulation timeline dict (from simulator engine).

    Returns:
        narrative_blocks dict with keys: eras, names, factions, regions,
        events, characters, legends, coherence_report
    """
    narrative_blocks: dict = {}

    logger.info("Starting full narration pipeline for '%s'", config.get("meta", {}).get("world_name", "?"))

    # Step 1: Era splitting
    logger.info("Step 1/9: Era splitting")
    narrative_blocks["eras"] = await _run_era_splitting(config, timeline)

    # Step 2: Naming
    logger.info("Step 2/9: Naming")
    narrative_blocks["names"] = await _run_naming(config, timeline)

    # Step 3: Faction sheets
    logger.info("Step 3/9: Faction sheets")
    narrative_blocks["factions"] = await _run_faction_sheets(config, timeline)

    # Step 4: Region sheets
    logger.info("Step 4/9: Region sheets")
    narrative_blocks["regions"] = await _run_region_sheets(config, timeline)

    # Step 5: Event narratives
    logger.info("Step 5/9: Event narratives")
    narrative_blocks["events"] = await _run_event_narratives(config, timeline, narrative_blocks)

    # Step 6: Character biographies
    logger.info("Step 6/9: Character biographies")
    narrative_blocks["characters"] = await _run_character_bios(config, timeline, narrative_blocks)

    # Step 7: Legends
    logger.info("Step 7/9: Legends")
    narrative_blocks["legends"] = await _run_legends(config, narrative_blocks)

    # Step 8: Entity extraction
    logger.info("Step 8/9: Entity extraction")
    narrative_blocks["entity_summary"] = await _run_entity_extraction(config, narrative_blocks, timeline)

    # Step 9: Coherence check with auto-fix loop
    logger.info("Step 9/9: Coherence check")
    narrative_blocks["coherence_report"] = await run_coherence_with_fix(config, narrative_blocks)

    logger.info(
        "Narration pipeline complete. Coherence score: %.2f",
        narrative_blocks.get("coherence_report", {}).get("score", 0),
    )

    return narrative_blocks


async def run_partial_narration(
    config: dict, timeline: dict, steps: list[str], existing_blocks: dict | None = None
) -> dict:
    """Run specific narration steps.

    Args:
        config: Validated world configuration dict.
        timeline: Simulation timeline dict.
        steps: List of step names to run.
        existing_blocks: Existing narrative_blocks to build upon.

    Returns:
        Updated narrative_blocks dict.
    """
    narrative_blocks = dict(existing_blocks or {})

    step_runners = {
        "era_splitting": lambda: _run_era_splitting(config, timeline),
        "naming": lambda: _run_naming(config, timeline),
        "faction_sheets": lambda: _run_faction_sheets(config, timeline),
        "region_sheets": lambda: _run_region_sheets(config, timeline),
        "event_narratives": lambda: _run_event_narratives(config, timeline, narrative_blocks),
        "character_bios": lambda: _run_character_bios(config, timeline, narrative_blocks),
        "legends": lambda: _run_legends(config, narrative_blocks),
        "entity_extraction": lambda: _run_entity_extraction(config, narrative_blocks, timeline),
        "coherence_check": lambda: _run_coherence_check(config, narrative_blocks),
    }

    block_keys = {
        "era_splitting": "eras",
        "naming": "names",
        "faction_sheets": "factions",
        "region_sheets": "regions",
        "event_narratives": "events",
        "character_bios": "characters",
        "legends": "legends",
        "entity_extraction": "entity_summary",
        "coherence_check": "coherence_report",
    }

    for step in steps:
        if step not in step_runners:
            logger.warning("Unknown narration step: '%s', skipping", step)
            continue
        logger.info("Running narration step: %s", step)
        result = await step_runners[step]()
        narrative_blocks[block_keys[step]] = result

    return narrative_blocks


# ── Internal step runners ────────────────────────────────────────────────────


async def _run_era_splitting(config: dict, timeline: dict) -> list[dict]:
    return await split_into_eras(config, timeline)


async def _run_naming(config: dict, timeline: dict) -> dict[str, str]:
    return await generate_names(config, timeline)


async def _run_faction_sheets(config: dict, timeline: dict) -> list[dict]:
    """Generate sheets for all factions."""
    genre = config.get("meta", {}).get("genre", "fantasy")
    factions_config = config.get("factions", [])

    # Build per-faction event history from timeline
    faction_events: dict[str, list] = {f["id"]: [] for f in factions_config}
    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for evt in tick.get("events", []):
            for fac_id in evt.get("involved_factions", []):
                if fac_id in faction_events:
                    faction_events[fac_id].append({
                        "year": year,
                        "event_id": evt.get("event_id"),
                        "outcome": evt.get("outcome", {}),
                    })

    sheets = []
    for fac in factions_config:
        fac_with_genre = {**fac, "_genre": genre}
        history = faction_events.get(fac["id"], [])
        sheet = await generate_faction_sheet(fac_with_genre, history)
        sheets.append(sheet)

    return sheets


async def _run_region_sheets(config: dict, timeline: dict) -> list[dict]:
    """Generate sheets for all regions."""
    genre = config.get("meta", {}).get("genre", "fantasy")
    regions_config = config.get("geography", {}).get("regions", [])

    # Build per-region event history from timeline
    region_events: dict[str, list] = {r["id"]: [] for r in regions_config}
    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for evt in tick.get("events", []):
            for reg_id in evt.get("involved_regions", []):
                if reg_id in region_events:
                    region_events[reg_id].append({
                        "year": year,
                        "event_id": evt.get("event_id"),
                    })

    sheets = []
    for reg in regions_config:
        reg_with_genre = {**reg, "_genre": genre}
        history = region_events.get(reg["id"], [])
        sheet = await generate_region_sheet(reg_with_genre, history)
        sheets.append(sheet)

    return sheets


async def _run_event_narratives(config: dict, timeline: dict, narrative_blocks: dict) -> list[dict]:
    """Extract events from timeline and narrate them."""
    eras = narrative_blocks.get("eras", [])
    if not eras:
        # Need eras first — run era splitting
        eras = await _run_era_splitting(config, timeline)
        narrative_blocks["eras"] = eras

    # Flatten all events from timeline with year info
    all_events = []
    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for evt in tick.get("events", []):
            all_events.append({**evt, "year": year})

    return await narrate_events(all_events, config, eras)


async def _run_character_bios(config: dict, timeline: dict, narrative_blocks: dict) -> list[dict]:
    """Extract characters from timeline and generate biographies."""
    names = narrative_blocks.get("names", {})
    if not names:
        names = await _run_naming(config, timeline)
        narrative_blocks["names"] = names

    characters = _extract_characters(timeline, config, names)
    return await generate_biographies(characters, config, names)


async def _run_legends(config: dict, narrative_blocks: dict) -> list[dict]:
    """Generate legends based on accumulated narrative content."""
    eras = narrative_blocks.get("eras", [])
    return await generate_legends(config, eras, narrative_blocks)


async def _run_coherence_check(config: dict, narrative_blocks: dict) -> dict:
    """Run coherence validation on all narrative content."""
    return await check_coherence(narrative_blocks, config)


async def _run_entity_extraction(config: dict, narrative_blocks: dict, timeline: dict | None = None) -> dict:
    """Run entity extraction per era (or iterative fallback)."""
    return await run_entity_extraction(config, narrative_blocks, timeline=timeline, max_depth=4)


async def run_coherence_with_fix(config: dict, narrative_blocks: dict) -> dict:
    """Run coherence check with auto-fix loop. Returns coherence report."""
    coherence_threshold = 0.75
    max_iterations = 3

    for iteration in range(1, max_iterations + 1):
        logger.info("Coherence check iteration %d/%d", iteration, max_iterations)
        report = await _run_coherence_check(config, narrative_blocks)

        score = report.get("score", 0.5)
        issues = report.get("issues", [])

        if score >= coherence_threshold or not issues:
            return report

        if iteration < max_iterations:
            await fix_coherence_issues(narrative_blocks, config, issues)
        else:
            report["warning"] = f"Score de cohérence ({score:.2f}) inférieur au seuil après {max_iterations} corrections."
            return report

    return report
