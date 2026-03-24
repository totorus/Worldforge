"""Export orchestrator — builds the full Bookstack wiki structure for a world."""

from __future__ import annotations

import logging
from typing import Any

from app.exporter.bookstack_client import BookstackClient
from app.exporter.formatters import (
    format_character_page,
    format_era_page,
    format_faction_page,
    format_legend_page,
    format_region_page,
    format_stats_page,
    format_tech_page,
)

logger = logging.getLogger("worldforge.exporter")


def _build_resource_index(config: dict) -> dict[str, str]:
    """Map resource id -> name from the config."""
    return {r["id"]: r.get("name", r["id"]) for r in config.get("resources", [])}


def _build_faction_index(config: dict) -> dict[str, dict]:
    """Map faction id -> faction config."""
    return {f["id"]: f for f in config.get("factions", [])}


def _build_region_index(config: dict) -> dict[str, dict]:
    """Map region id -> region config."""
    return {
        r["id"]: r for r in config.get("geography", {}).get("regions", [])
    }


def _build_tech_index(config: dict) -> dict[str, dict]:
    """Map tech id -> tech node."""
    return {t["id"]: t for t in config.get("tech_tree", {}).get("nodes", [])}


def _group_events_by_era(
    eras: list[dict], events: list[dict]
) -> dict[str, list[dict]]:
    """Assign timeline events to the era they fall in (by year range)."""
    era_events: dict[str, list[dict]] = {era.get("id", era.get("name", "")): [] for era in eras}

    for ev in events:
        year = ev.get("year")
        if year is None:
            continue
        for era in eras:
            era_key = era.get("id", era.get("name", ""))
            start = era.get("start_year", 0)
            end = era.get("end_year", float("inf"))
            if start <= year <= end:
                era_events[era_key].append(ev)
                break
    return era_events


async def export_to_bookstack(
    config: dict,
    timeline: dict,
    narrative_blocks: dict,
    world_name: str,
) -> dict[str, Any]:
    """Create the full Bookstack wiki for a world.

    Parameters
    ----------
    config:
        The world configuration (meta, geography, factions, tech_tree, etc.).
    timeline:
        The simulation output (events, characters, faction_states, eras, ...).
    narrative_blocks:
        LLM-generated narrative content keyed by type
        (regions, factions, eras, characters, legends, coherence_report, ...).
    world_name:
        Display name for the world.

    Returns
    -------
    A mapping dict suitable for storage in ``world.bookstack_mapping``.
    """
    client = BookstackClient()

    # Indexes
    faction_idx = _build_faction_index(config)
    region_idx = _build_region_index(config)
    tech_idx = _build_tech_index(config)

    book_ids: dict[str, int] = {}
    mapping: dict[str, Any] = {"books": {}}

    # ------------------------------------------------------------------
    # 1. Create the 7 books
    # ------------------------------------------------------------------
    book_defs = [
        ("atlas", "Atlas", "Géographie du monde"),
        ("chroniques", "Chroniques", "Histoire par ères"),
        ("factions", "Factions", "Peuples et organisations"),
        ("personnages", "Personnages", "Personnages notables"),
        ("tech", "Technologies & Pouvoirs", "Arbre technologique et pouvoirs"),
        ("legendes", "Légendes", "Mythes et légendes"),
        ("annexes", "Annexes", "Configuration et statistiques"),
    ]

    for key, name, desc in book_defs:
        book = await client.create_book(f"{world_name} — {name}", desc)
        book_ids[key] = book["id"]
        mapping["books"][key] = book["id"]
        logger.info("Created book '%s' (id=%d)", name, book["id"])

    # ------------------------------------------------------------------
    # 2. Shelf — created after books so we can attach them
    # ------------------------------------------------------------------
    shelf = await client.create_shelf(
        world_name,
        description=f"Encyclopédie du monde : {world_name}",
        books=list(book_ids.values()),
    )
    mapping["shelf_id"] = shelf["id"]
    logger.info("Created shelf '%s' (id=%d)", world_name, shelf["id"])

    # ------------------------------------------------------------------
    # 3. Atlas — regions
    # ------------------------------------------------------------------
    region_sheets = narrative_blocks.get("regions", {})
    for region in config.get("geography", {}).get("regions", []):
        rid = region["id"]
        rname = region.get("name", rid)
        chapter = await client.create_chapter(book_ids["atlas"], rname)

        sheet = region_sheets.get(rid, {})
        html = format_region_page(region, sheet if isinstance(sheet, dict) else None)
        await client.create_page(chapter_id=chapter["id"], name=rname, html=html)

    # ------------------------------------------------------------------
    # 4. Chroniques — eras + events
    # ------------------------------------------------------------------
    eras = timeline.get("eras", narrative_blocks.get("eras", []))
    tl_events = timeline.get("events", [])
    era_events = _group_events_by_era(eras, tl_events)

    narrative_eras = narrative_blocks.get("eras", {})

    for era in eras:
        era_key = era.get("id", era.get("name", "Ère"))
        era_name = era.get("name", era_key)

        # Merge narrative description into era dict if available
        if isinstance(narrative_eras, dict) and era_key in narrative_eras:
            narr = narrative_eras[era_key]
            if isinstance(narr, dict):
                era = {**era, **narr}
            elif isinstance(narr, str):
                era = {**era, "description": narr}

        chapter = await client.create_chapter(book_ids["chroniques"], era_name)
        events = era_events.get(era_key, [])
        html = format_era_page(era, events)
        await client.create_page(chapter_id=chapter["id"], name=era_name, html=html)

    # ------------------------------------------------------------------
    # 5. Factions
    # ------------------------------------------------------------------
    faction_sheets = narrative_blocks.get("factions", {})
    for faction in config.get("factions", []):
        fid = faction["id"]
        fname = faction.get("name", fid)
        chapter = await client.create_chapter(book_ids["factions"], fname)

        sheet = faction_sheets.get(fid, {})
        html = format_faction_page(faction, sheet if isinstance(sheet, dict) else None)
        await client.create_page(chapter_id=chapter["id"], name=f"Fiche — {fname}", html=html)

    # ------------------------------------------------------------------
    # 6. Personnages
    # ------------------------------------------------------------------
    characters = timeline.get("characters", [])
    character_bios = narrative_blocks.get("characters", {})
    for char in characters:
        cid = char.get("id", char.get("name", ""))
        cname = char.get("name", cid)
        chapter = await client.create_chapter(book_ids["personnages"], cname)

        bio = character_bios.get(cid, character_bios.get(cname))
        bio_text = bio if isinstance(bio, str) else (bio.get("biography") if isinstance(bio, dict) else None)
        html = format_character_page(char, bio_text)
        await client.create_page(chapter_id=chapter["id"], name=cname, html=html)

    # ------------------------------------------------------------------
    # 7. Technologies & Pouvoirs
    # ------------------------------------------------------------------
    tech_narratives = narrative_blocks.get("technologies", narrative_blocks.get("tech", {}))
    for tech in config.get("tech_tree", {}).get("nodes", []):
        tid = tech["id"]
        tname = tech.get("name", tid)

        # Merge narrative if available
        narr = tech_narratives.get(tid) if isinstance(tech_narratives, dict) else None
        merged = {**tech}
        if isinstance(narr, dict):
            merged.update(narr)
        elif isinstance(narr, str):
            merged["description"] = narr

        html = format_tech_page(merged)
        await client.create_page(book_id=book_ids["tech"], name=tname, html=html)

    # ------------------------------------------------------------------
    # 8. Légendes
    # ------------------------------------------------------------------
    legends = narrative_blocks.get("legends", [])
    if isinstance(legends, list):
        for legend in legends:
            title = legend.get("title", legend.get("name", "Légende"))
            html = format_legend_page(legend)
            await client.create_page(book_id=book_ids["legendes"], name=title, html=html)
    elif isinstance(legends, dict):
        for key, legend in legends.items():
            if isinstance(legend, dict):
                title = legend.get("title", legend.get("name", key))
                html = format_legend_page(legend)
            else:
                title = key
                html = f"<p>{legend}</p>"
            await client.create_page(book_id=book_ids["legendes"], name=title, html=html)

    # ------------------------------------------------------------------
    # 9. Annexes — config summary + stats + coherence report
    # ------------------------------------------------------------------
    stats_html = format_stats_page(config, timeline)
    await client.create_page(
        book_id=book_ids["annexes"],
        name="Configuration & Statistiques",
        html=stats_html,
    )

    coherence = narrative_blocks.get("coherence_report", "")
    if coherence:
        coh_html = (
            f"<h2>Rapport de cohérence</h2>"
            f"<p>{coherence}</p>" if isinstance(coherence, str) else f"<h2>Rapport de cohérence</h2><p>{coherence}</p>"
        )
        await client.create_page(
            book_id=book_ids["annexes"],
            name="Rapport de cohérence",
            html=coh_html,
        )

    # ------------------------------------------------------------------
    # Build public URL
    # ------------------------------------------------------------------
    from app.config import settings

    base = settings.bookstack_url.rstrip("/")
    mapping["public_url"] = f"{base}/shelves/{shelf['slug']}" if shelf.get("slug") else f"{base}/shelves/{shelf['id']}"

    logger.info("Export complete for world '%s'", world_name)
    return mapping


async def sync_to_bookstack(
    config: dict,
    timeline: dict,
    narrative_blocks: dict,
    world_name: str,
    existing_mapping: dict,
) -> dict[str, Any]:
    """Re-export: delete and recreate.

    For a v1 implementation we simply re-run the full export.
    A smarter diff-based sync can be added later.
    """
    # For now, just re-create everything (Bookstack doesn't mind duplicate
    # names on different entities).  A future version could update pages
    # in-place using the stored mapping.
    return await export_to_bookstack(config, timeline, narrative_blocks, world_name)
