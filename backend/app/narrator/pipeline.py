"""Narration pipeline orchestrator — runs all narrative enrichment steps sequentially."""

import logging
import time

from app.narrator.eras import split_into_eras
from app.narrator.naming import generate_names
from app.narrator.sheets import generate_faction_sheet, generate_region_sheet
from app.narrator.events_narrator import narrate_events
from app.narrator.characters_narrator import generate_biographies, _extract_characters
from app.narrator.legends import generate_legends
from app.narrator.coherence import check_coherence
from app.narrator.entity_extraction import run_entity_extraction
from app.narrator.coherence_fix import fix_coherence_issues
from app.narrator.pre_validation import pre_validate
from app.narrator.schemas import validate_step_output

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


def _count_items(data) -> int:
    """Count the number of items produced by a step."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # For names dict, count entries; for reports, count 1
        return len(data)
    return 1


async def run_narration(config: dict, timeline: dict) -> dict:
    """Run the full narration pipeline on a simulated world.

    Calls each step sequentially:
        era_splitting -> naming -> faction_sheets -> region_sheets ->
        event_narratives -> character_bios -> legends -> entity_extraction -> coherence_check

    Args:
        config: Validated world configuration dict.
        timeline: Simulation timeline dict (from simulator engine).

    Returns:
        narrative_blocks dict with keys: eras, names, factions, regions,
        events, characters, legends, entity_summary, coherence_report, _run_report
    """
    narrative_blocks: dict = {}
    run_report: dict = {"steps": {}, "start_time": time.time()}

    world_name = config.get("meta", {}).get("world_name", "?")
    logger.info("Starting full narration pipeline for '%s'", world_name)

    steps = [
        ("eras", "Step 1/9: Era splitting", lambda: _run_era_splitting(config, timeline)),
        ("names", "Step 2/9: Naming", lambda: _run_naming(config, timeline)),
        ("factions", "Step 3/9: Faction sheets", lambda: _run_faction_sheets(config, timeline)),
        ("regions", "Step 4/9: Region sheets", lambda: _run_region_sheets(config, timeline)),
        ("events", "Step 5/9: Event narratives", lambda: _run_event_narratives(config, timeline, narrative_blocks)),
        ("characters", "Step 6/9: Character bios", lambda: _run_character_bios(config, timeline, narrative_blocks)),
        ("legends", "Step 7/9: Legends", lambda: _run_legends(config, narrative_blocks)),
        ("entity_summary", "Step 8/9: Entity extraction", lambda: _run_entity_extraction(config, narrative_blocks, timeline)),
        ("coherence_report", "Step 9/9: Coherence check", lambda: run_coherence_with_fix(config, narrative_blocks)),
    ]

    for step_key, label, runner in steps:
        logger.info(label)
        step_start = time.time()
        step_report = {"status": "running", "errors": []}

        try:
            result = await runner()

            # Validate with Pydantic schema
            validated, validation_errors = validate_step_output(step_key, result)
            if validation_errors:
                for err in validation_errors:
                    logger.warning(err)
                step_report["validation_warnings"] = validation_errors

            narrative_blocks[step_key] = validated
            step_report["status"] = "ok"
            step_report["items_produced"] = _count_items(validated)

        except Exception as e:
            logger.error("Step '%s' failed: %s: %s", step_key, type(e).__name__, str(e)[:500])
            step_report["status"] = "failed"
            step_report["errors"].append(f"{type(e).__name__}: {str(e)[:300]}")
            # Don't abort pipeline — set empty result and continue
            narrative_blocks[step_key] = [] if step_key not in ("names", "coherence_report", "entity_summary") else {}

        step_report["duration_s"] = round(time.time() - step_start, 1)
        run_report["steps"][step_key] = step_report

    run_report["total_duration_s"] = round(time.time() - run_report["start_time"], 1)
    del run_report["start_time"]
    run_report["coherence_score"] = narrative_blocks.get("coherence_report", {}).get("score", 0)
    narrative_blocks["_run_report"] = run_report

    logger.info(
        "Narration pipeline complete in %.0fs. Coherence score: %.2f",
        run_report["total_duration_s"],
        run_report["coherence_score"],
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
        try:
            result = await step_runners[step]()
            block_key = block_keys[step]
            validated, validation_errors = validate_step_output(block_key, result)
            if validation_errors:
                for err in validation_errors:
                    logger.warning(err)
            narrative_blocks[block_key] = validated
        except Exception as e:
            logger.error("Partial step '%s' failed: %s: %s", step, type(e).__name__, str(e)[:500])
            block_key = block_keys[step]
            narrative_blocks[block_key] = [] if block_key not in ("names", "coherence_report", "entity_summary") else {}

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


async def _run_event_narratives(config: dict, timeline: dict, narrative_blocks: dict, *, registry=None) -> list[dict]:
    """Extract events from timeline and narrate them."""
    eras = narrative_blocks.get("eras", [])
    if not eras:
        eras = await _run_era_splitting(config, timeline)
        narrative_blocks["eras"] = eras

    # Flatten all events from timeline with year info
    all_events = []
    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for evt in tick.get("events", []):
            all_events.append({**evt, "year": year})

    return await narrate_events(all_events, config, eras, registry=registry)


async def _run_character_bios(config: dict, timeline: dict, narrative_blocks: dict, *, registry=None) -> list[dict]:
    """Extract characters from timeline and generate biographies."""
    names = narrative_blocks.get("names", {})
    if not names:
        names = await _run_naming(config, timeline)
        narrative_blocks["names"] = names

    characters = _extract_characters(timeline, config, names)
    return await generate_biographies(
        characters, config, names,
        registry=registry,
        eras=narrative_blocks.get("eras", []),
        events=narrative_blocks.get("events", []),
    )


async def _run_legends(config: dict, narrative_blocks: dict, *, registry=None) -> list[dict]:
    """Generate legends based on accumulated narrative content."""
    eras = narrative_blocks.get("eras", [])
    return await generate_legends(config, eras, narrative_blocks, registry=registry)


async def _run_coherence_check(config: dict, narrative_blocks: dict, *, registry=None) -> dict:
    """Run coherence validation on all narrative content."""
    return await check_coherence(narrative_blocks, config, registry=registry)


async def _run_entity_extraction(config: dict, narrative_blocks: dict, timeline: dict | None = None) -> dict:
    """Run entity extraction per era (or iterative fallback)."""
    return await run_entity_extraction(config, narrative_blocks, timeline=timeline, max_depth=2)


async def run_coherence_with_fix(config: dict, narrative_blocks: dict, *, registry=None) -> dict:
    """Run coherence check with single auto-fix pass. Returns coherence report."""
    # Programmatic pre-validation: fix obvious issues without LLM
    pre_fixes = pre_validate(narrative_blocks, config)
    if pre_fixes:
        logger.info("Pre-validation applied %d deterministic fixes before coherence check", pre_fixes)

    coherence_threshold = 0.75
    max_iterations = 2  # 1 check + 1 fix + 1 recheck

    for iteration in range(1, max_iterations + 1):
        logger.info("Coherence check iteration %d/%d", iteration, max_iterations)
        report = await _run_coherence_check(config, narrative_blocks, registry=registry)

        score = report.get("score", 0.5)
        issues = report.get("issues", [])

        if score >= coherence_threshold or not issues:
            return report

        if iteration < max_iterations:
            await fix_coherence_issues(narrative_blocks, config, issues)
        else:
            report["warning"] = f"Score de cohérence ({score:.2f}) inférieur au seuil après correction."
            return report

    return report
