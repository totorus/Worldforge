"""Export orchestrator — builds the full Bookstack wiki structure for a world.

Structure:
  Shelf "WorldForge" (shared, created once)
    └── Book "<world_name>"
          ├── Chapter "Atlas"         → one page per region
          ├── Chapter "Chroniques"    → one page per era
          ├── Chapter "Factions"      → one page per faction
          ├── Chapter "Personnages"   → one page per character
          ├── Chapter "Technologies & Pouvoirs" → one page per tech
          ├── Chapter "Légendes"      → one page per legend
          └── Chapter "Annexes"       → config + stats + coherence
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
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

SHELF_NAME = "WorldForge"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _list_to_dict(items: list | dict, key: str = "id") -> dict[str, dict]:
    """Normalize: accept a list of dicts or a dict keyed by id.

    On duplicate keys, keep the entry with the most content (longest
    biography/description/narrative) to prefer richer, more coherent data.
    """
    if isinstance(items, dict):
        return items
    if isinstance(items, list):
        result: dict[str, dict] = {}
        for item in items:
            if isinstance(item, dict):
                k = item.get(key, item.get("name", ""))
                existing = result.get(k)
                if existing is None:
                    result[k] = item
                else:
                    # Keep the entry with more content
                    def _content_len(d: dict) -> int:
                        return sum(
                            len(v) for v in d.values()
                            if isinstance(v, str)
                        )
                    if _content_len(item) > _content_len(existing):
                        result[k] = item
        return result
    return {}


def _group_events_by_era(
    eras: list[dict], events: list[dict]
) -> dict[str, list[dict]]:
    """Assign timeline events to the era they fall in (by year range)."""
    era_events: dict[str, list[dict]] = {
        era.get("id", era.get("name", "")): [] for era in eras
    }
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


def _inject_cross_references(html: str, xref_map: dict[str, str]) -> str:
    """Replace entity name mentions in HTML with <a> links.

    xref_map: {entity_name: page_url}
    Matches whole words only, avoids replacing inside existing tags/links.
    """
    if not xref_map or not html:
        return html

    # Sort by length descending so longer names match first
    sorted_names = sorted(xref_map.keys(), key=len, reverse=True)

    for name in sorted_names:
        url = xref_map[name]
        pattern = re.compile(
            r'(?<![">])(?<!/)\b(' + re.escape(name) + r')\b(?![^<]*>)(?![^<]*</a>)',
            re.IGNORECASE,
        )
        # Only replace first occurrence per page to avoid over-linking
        html = pattern.sub(rf'<a href="{url}">\1</a>', html, count=1)

    return html


# ------------------------------------------------------------------
# Main export
# ------------------------------------------------------------------

async def export_to_bookstack(
    config: dict,
    timeline: dict,
    narrative_blocks: dict,
    world_name: str,
) -> dict[str, Any]:
    """Create the full Bookstack wiki for a world.

    Handles both dict-indexed and list-based narrative_blocks.

    Returns a mapping dict suitable for storage in ``world.bookstack_mapping``.
    """
    client = BookstackClient()

    public_base = (settings.bookstack_public_url or settings.bookstack_url).rstrip("/")

    # ------------------------------------------------------------------
    # 1. Find or create the shared "WorldForge" shelf
    # ------------------------------------------------------------------
    shelf = await client.find_shelf_by_name(SHELF_NAME)
    if shelf is None:
        shelf = await client.create_shelf(
            SHELF_NAME, description="Mondes générés par WorldForge"
        )
        logger.info("Created shelf '%s' (id=%d)", SHELF_NAME, shelf["id"])
    else:
        logger.info("Reusing shelf '%s' (id=%d)", SHELF_NAME, shelf["id"])

    # ------------------------------------------------------------------
    # 2. Create one book for this world
    # ------------------------------------------------------------------
    book = await client.create_book(world_name, f"Encyclopédie du monde : {world_name}")
    book_id = book["id"]
    logger.info("Created book '%s' (id=%d)", world_name, book_id)

    # Attach book to shelf
    existing_books = shelf.get("books", [])
    existing_book_ids = [
        b["id"] for b in existing_books
        if isinstance(b, dict)
    ] if isinstance(existing_books, list) else []
    await client.attach_book_to_shelf(shelf["id"], existing_book_ids + [book_id])

    # ------------------------------------------------------------------
    # 3. Create the 7 chapters
    # ------------------------------------------------------------------
    chapter_defs = [
        ("atlas", "Atlas", "Géographie du monde"),
        ("chroniques", "Chroniques", "Histoire par ères"),
        ("factions", "Factions", "Peuples et organisations"),
        ("personnages", "Personnages", "Personnages notables"),
        ("tech", "Technologies & Pouvoirs", "Arbre technologique et pouvoirs"),
        ("legendes", "Légendes", "Mythes et légendes"),
        ("annexes", "Annexes", "Configuration et statistiques"),
    ]

    chapter_ids: dict[str, int] = {}
    for key, name, desc in chapter_defs:
        chapter = await client.create_chapter(book_id, name, desc)
        chapter_ids[key] = chapter["id"]
        logger.info("  Chapter '%s' (id=%d)", name, chapter["id"])

    # ------------------------------------------------------------------
    # Normalize narrative_blocks to dicts keyed by id/name
    # ------------------------------------------------------------------
    narr_regions = _list_to_dict(narrative_blocks.get("regions", {}))
    narr_factions = _list_to_dict(narrative_blocks.get("factions", {}))
    narr_characters = _list_to_dict(narrative_blocks.get("characters", {}), key="name")
    narr_eras_raw = narrative_blocks.get("eras", [])
    narr_eras = _list_to_dict(narr_eras_raw, key="name") if isinstance(narr_eras_raw, list) else narr_eras_raw
    narr_events = narrative_blocks.get("events", [])
    if isinstance(narr_events, list):
        narr_events_by_era: dict[str, list[dict]] = {}
        for ev in narr_events:
            era_name = ev.get("era", "")
            narr_events_by_era.setdefault(era_name, []).append(ev)
    else:
        narr_events_by_era = {}

    # ------------------------------------------------------------------
    # Collect all pages (pass 1)
    # ------------------------------------------------------------------
    pages_created: list[dict[str, Any]] = []

    # --- Build ID → name indexes for resolving internal IDs ---
    config_regions = config.get("geography", {}).get("regions", [])
    region_names = {r["id"]: r.get("name", r["id"]) for r in config_regions}
    resource_names = {r["id"]: r.get("name", r["id"]) for r in config.get("resources", [])}
    event_names = {e["id"]: e.get("name", e["id"]) for e in config.get("event_pool", [])}
    # Merge all into a single ID resolver
    id_names = {**region_names, **resource_names, **event_names}

    # --- Atlas ---
    for region in config_regions:
        rid = region["id"]
        rname = region.get("name", rid)
        narr = narr_regions.get(rid, narr_regions.get(rname, {}))
        html = format_region_page(region, narr if isinstance(narr, dict) else None, id_names=id_names)
        page = await client.create_page(
            chapter_id=chapter_ids["atlas"], name=rname, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": rname, "type": "region", "key": rid})

    # --- Chroniques ---
    # Use narrative eras if richer, fall back to timeline eras
    timeline_eras = timeline.get("eras", [])
    if isinstance(narr_eras_raw, list) and narr_eras_raw:
        eras_to_use = narr_eras_raw
    else:
        eras_to_use = timeline_eras

    # Group timeline events by era for enrichment
    tl_events = timeline.get("events", [])
    era_events = _group_events_by_era(eras_to_use, tl_events)

    for era in eras_to_use:
        era_key = era.get("id", era.get("name", "Ère"))
        era_name = era.get("name", era_key)

        # Merge narrative era data if available (dict format)
        if isinstance(narr_eras, dict) and era_key in narr_eras:
            extra = narr_eras[era_key]
            if isinstance(extra, dict):
                era = {**era, **extra}

        # Merge narrative events for this era
        narrative_evts = narr_events_by_era.get(era_name, [])
        sim_events = era_events.get(era_key, [])

        html = format_era_page(era, sim_events, narrative_evts)
        page = await client.create_page(
            chapter_id=chapter_ids["chroniques"], name=era_name, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": era_name, "type": "era", "key": era_key})

    # --- Factions ---
    for faction in config.get("factions", []):
        fid = faction["id"]
        fname = faction.get("name", fid)
        narr = narr_factions.get(fid, narr_factions.get(fname, {}))
        html = format_faction_page(faction, narr if isinstance(narr, dict) else None, id_names=id_names)
        page = await client.create_page(
            chapter_id=chapter_ids["factions"], name=fname, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": fname, "type": "faction", "key": fid})

    # --- Personnages ---
    # Export all characters from narrative_blocks as-is (one page each)
    raw_characters = narrative_blocks.get("characters", [])
    all_characters = raw_characters if isinstance(raw_characters, list) else list(raw_characters.values()) if isinstance(raw_characters, dict) else []

    for char in all_characters:
        if not isinstance(char, dict):
            continue
        cname = char.get("name", "Personnage inconnu")
        html = format_character_page(char)
        page = await client.create_page(
            chapter_id=chapter_ids["personnages"], name=cname, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": cname, "type": "character", "key": cname})

    # --- Technologies ---
    tech_narratives = narrative_blocks.get("technologies", narrative_blocks.get("tech", {}))
    if isinstance(tech_narratives, list):
        tech_narratives = _list_to_dict(tech_narratives)

    for tech in config.get("tech_tree", {}).get("nodes", []):
        tid = tech["id"]
        tname = tech.get("name", tid)
        narr = tech_narratives.get(tid) if isinstance(tech_narratives, dict) else None
        merged = {**tech}
        if isinstance(narr, dict):
            merged.update(narr)
        elif isinstance(narr, str):
            merged["description"] = narr
        html = format_tech_page(merged)
        page = await client.create_page(
            chapter_id=chapter_ids["tech"], name=tname, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": tname, "type": "tech", "key": tid})

    # --- Légendes ---
    legends_raw = narrative_blocks.get("legends", [])
    legend_items: list[dict] = []
    if isinstance(legends_raw, list):
        legend_items = [l for l in legends_raw if isinstance(l, dict)]
    elif isinstance(legends_raw, dict):
        for k, v in legends_raw.items():
            if isinstance(v, dict):
                legend_items.append({**v, "title": v.get("title", v.get("name", k))})
            else:
                legend_items.append({"title": k, "text": str(v)})

    for legend in legend_items:
        title = legend.get("title", legend.get("name", "Légende"))
        html = format_legend_page(legend)
        page = await client.create_page(
            chapter_id=chapter_ids["legendes"], name=title, html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": title, "type": "legend", "key": title})

    # --- Annexes ---
    stats_html = format_stats_page(config, timeline)
    page = await client.create_page(
        chapter_id=chapter_ids["annexes"],
        name="Configuration & Statistiques",
        html=stats_html,
    )
    pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": "Configuration & Statistiques", "type": "annex", "key": "stats"})

    coherence = narrative_blocks.get("coherence_report", "")
    if coherence:
        if isinstance(coherence, dict):
            score = coherence.get("score", "?")
            issues = coherence.get("issues", [])
            suggestions = coherence.get("suggestions", [])
            coh_parts = [f"<h2>Rapport de cohérence</h2>", f"<p><strong>Score :</strong> {score}</p>"]
            if issues:
                coh_parts.append("<h3>Problèmes identifiés</h3><ul>")
                coh_parts.extend(f"<li>{i}</li>" for i in issues)
                coh_parts.append("</ul>")
            if suggestions:
                coh_parts.append("<h3>Suggestions</h3><ul>")
                coh_parts.extend(f"<li>{s}</li>" for s in suggestions)
                coh_parts.append("</ul>")
            coh_html = "\n".join(coh_parts)
        else:
            coh_html = f"<h2>Rapport de cohérence</h2><p>{coherence}</p>"

        page = await client.create_page(
            chapter_id=chapter_ids["annexes"],
            name="Rapport de cohérence",
            html=coh_html,
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": "Rapport de cohérence", "type": "annex", "key": "coherence"})

    # ------------------------------------------------------------------
    # Pass 2: inject cross-references
    # ------------------------------------------------------------------
    book_slug = book.get("slug", str(book_id))
    xref_map: dict[str, str] = {}
    for p in pages_created:
        if p["type"] in ("annex",):
            continue
        page_slug = p["slug"] or str(p["id"])
        xref_map[p["name"]] = f"{public_base}/books/{book_slug}/page/{page_slug}"

    logger.info("Cross-reference index: %d entries", len(xref_map))

    for p in pages_created:
        page_data = await client._get(f"/pages/{p['id']}")
        original_html = page_data.get("html", "")
        self_xref = {k: v for k, v in xref_map.items() if k != p["name"]}
        updated_html = _inject_cross_references(original_html, self_xref)
        if updated_html != original_html:
            await client.update_page(p["id"], html=updated_html)
            logger.debug("  Updated cross-refs for page '%s'", p["name"])

    # ------------------------------------------------------------------
    # Build mapping
    # ------------------------------------------------------------------
    pages_mapping = {}
    for p in pages_created:
        pages_mapping[p["key"]] = {
            "id": p["id"], "slug": p["slug"],
            "name": p["name"], "type": p["type"],
        }

    mapping: dict[str, Any] = {
        "shelf_id": shelf["id"],
        "book_id": book_id,
        "chapters": chapter_ids,
        "pages": pages_mapping,
        "public_url": f"{public_base}/books/{book_slug}",
    }

    logger.info("Export complete for world '%s'", world_name)
    return mapping


async def sync_to_bookstack(
    config: dict,
    timeline: dict,
    narrative_blocks: dict,
    world_name: str,
    existing_mapping: dict,
) -> dict[str, Any]:
    """Re-export: full recreate for now."""
    return await export_to_bookstack(config, timeline, narrative_blocks, world_name)
