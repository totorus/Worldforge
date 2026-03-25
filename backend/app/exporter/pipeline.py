"""Export orchestrator — builds the full Bookstack wiki structure for a world.

Structure:
  Shelf "WorldForge" (shared, created once)
    └── Book "<world_name>"
          ├── Chapter "Atlas"         → one page per region
          ├── Chapter "Chroniques"    → one page per era
          ├── Chapter "Factions"      → one page per faction
          ├── Chapter "Races & Peuples" → one page per race
          ├── Chapter "Cosmogonies"   → one page per cosmogony
          ├── Chapter "Personnages"   → one page per character
          ├── Chapter "Technologies & Pouvoirs" → one page per tech
          ├── Chapter "Légendes"      → one page per legend
          ├── Chapter "Faune"         → one page per fauna entity
          ├── Chapter "Flore"         → one page per flora entity
          ├── Chapter "Bestiaire"     → one page per bestiary entity
          ├── Chapter "Lieux notables" → one page per notable location
          ├── Chapter "Ressources"    → one page per resource
          ├── Chapter "Organisations" → one page per organization
          ├── Chapter "Artefacts"     → one page per artifact
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
    format_race_page,
    format_cosmogony_page,
    format_fauna_page,
    format_flora_page,
    format_bestiary_page,
    format_notable_location_page,
    format_resource_page,
    format_organization_page,
    format_artifact_page,
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


def _match_narrative_events_to_eras(
    events: list[dict], eras: list[dict]
) -> dict[str, list[dict]]:
    """Assign narrative events to eras using cascading matching.
    Cascade: exact name → substring inclusion → year range → orphans.
    """
    result: dict[str, list[dict]] = {era.get("name", ""): [] for era in eras}
    result["__orphans__"] = []

    for ev in events:
        era_field = ev.get("era", "")
        matched = False

        # 1. Exact match
        if era_field in result and era_field != "__orphans__":
            result[era_field].append(ev)
            continue

        # 2. Substring inclusion (case-insensitive)
        era_lower = era_field.lower()
        for era in eras:
            era_name = era.get("name", "")
            if era_name.lower() in era_lower or era_lower in era_name.lower():
                result[era_name].append(ev)
                matched = True
                break

        if matched:
            continue

        # 3. Year-range fallback
        year = ev.get("year")
        if year is not None:
            for era in eras:
                start = era.get("start_year", 0)
                end = era.get("end_year", float("inf"))
                if start <= year <= end:
                    result[era.get("name", "")].append(ev)
                    matched = True
                    break

        if not matched:
            result["__orphans__"].append(ev)

    return result


def _collect_unlocked_techs(
    timeline: dict, tech_tree_nodes: dict[str, dict]
) -> list[dict]:
    """Collect techs unlocked by any faction across all ticks.
    Uses the last tick's world_state for the final cumulative state.
    """
    ticks = timeline.get("ticks", [])
    if not ticks:
        return []

    unlocked_ids: set[str] = set()
    last_tick = ticks[-1]
    factions = last_tick.get("world_state", {}).get("factions", [])
    for fac in factions:
        for tech_id in fac.get("unlocked_techs", []):
            unlocked_ids.add(tech_id)

    # Fallback: scan all ticks if last tick had nothing
    if not unlocked_ids:
        for tick in ticks:
            for fac in tick.get("world_state", {}).get("factions", []):
                for tech_id in fac.get("unlocked_techs", []):
                    unlocked_ids.add(tech_id)

    result = []
    for tech_id in sorted(unlocked_ids):
        node = tech_tree_nodes.get(tech_id)
        if node:
            result.append(node)
        else:
            result.append({"id": tech_id, "name": tech_id})
    return result


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
    # 3. Create chapters
    # ------------------------------------------------------------------
    chapter_defs = [
        ("atlas", "Atlas", "Géographie du monde"),
        ("chroniques", "Chroniques", "Histoire par ères"),
        ("factions", "Factions", "Peuples et organisations"),
        ("races", "Races & Peuples", "Races et peuples du monde"),
        ("cosmogonies", "Cosmogonies", "Mythes de création"),
        ("personnages", "Personnages", "Personnages notables"),
        ("tech", "Technologies & Pouvoirs", "Arbre technologique et pouvoirs"),
        ("legendes", "Légendes", "Mythes et légendes"),
        ("faune", "Faune", "Animaux notables du monde"),
        ("flore", "Flore", "Plantes notables du monde"),
        ("bestiaire", "Bestiaire", "Créatures magiques et êtres uniques"),
        ("lieux", "Lieux notables", "Lieux remarquables du monde"),
        ("ressources", "Ressources", "Ressources uniques du monde"),
        ("organisations", "Organisations", "Ordres, guildes et confréries"),
        ("artefacts", "Artefacts", "Objets légendaires et reliques"),
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

    narr_events = narrative_blocks.get("events", [])
    if isinstance(narr_events, list):
        narr_events_by_era = _match_narrative_events_to_eras(narr_events, eras_to_use)
    else:
        narr_events_by_era = {}

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

    # Orphan events (no era match)
    orphan_events = narr_events_by_era.get("__orphans__", [])
    if orphan_events:
        orphan_era = {"name": "Événements non classés", "narrative": "Événements n'ayant pu être associés à une ère définie."}
        html = format_era_page(orphan_era, [], orphan_events)
        page = await client.create_page(
            chapter_id=chapter_ids["chroniques"], name="Événements non classés", html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": "Événements non classés", "type": "era", "key": "__orphans__"})

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

    # --- Technologies (only unlocked) ---
    tech_narratives = narrative_blocks.get("technologies", narrative_blocks.get("tech", {}))
    if isinstance(tech_narratives, list):
        tech_narratives = _list_to_dict(tech_narratives)

    # tech_tree.nodes can be a list or dict — normalize to dict
    raw_nodes = config.get("tech_tree", {}).get("nodes", [])
    if isinstance(raw_nodes, list):
        tech_nodes_dict = {t["id"]: t for t in raw_nodes if isinstance(t, dict) and "id" in t}
    elif isinstance(raw_nodes, dict):
        tech_nodes_dict = raw_nodes
    else:
        tech_nodes_dict = {}

    unlocked_techs = _collect_unlocked_techs(timeline, tech_nodes_dict)

    for tech in unlocked_techs:
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

    # --- Races ---
    for race in narrative_blocks.get("entities_race", []):
        if not isinstance(race, dict):
            continue
        rname = race.get("name", "Race inconnue")
        html = format_race_page(race)
        page = await client.create_page(chapter_id=chapter_ids["races"], name=rname, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": rname, "type": "race", "key": rname})

    # --- Cosmogonies ---
    for cosmo in narrative_blocks.get("entities_cosmogonie", []):
        if not isinstance(cosmo, dict):
            continue
        cname = cosmo.get("name", "Cosmogonie inconnue")
        html = format_cosmogony_page(cosmo)
        page = await client.create_page(chapter_id=chapter_ids["cosmogonies"], name=cname, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": cname, "type": "cosmogony", "key": cname})

    # --- Faune ---
    for entity in narrative_blocks.get("entities_faune", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_fauna_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["faune"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "fauna", "key": ename})

    # --- Flore ---
    for entity in narrative_blocks.get("entities_flore", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_flora_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["flore"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "flora", "key": ename})

    # --- Bestiaire ---
    for entity in narrative_blocks.get("entities_bestiaire", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_bestiary_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["bestiaire"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "bestiary", "key": ename})

    # --- Lieux notables ---
    for entity in narrative_blocks.get("entities_lieu_notable", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_notable_location_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["lieux"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "location", "key": ename})

    # --- Ressources ---
    for entity in narrative_blocks.get("entities_ressource", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_resource_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["ressources"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "resource", "key": ename})

    # --- Organisations ---
    for entity in narrative_blocks.get("entities_organisation", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_organization_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["organisations"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "organization", "key": ename})

    # --- Artefacts ---
    for entity in narrative_blocks.get("entities_artefact", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_artifact_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["artefacts"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "artifact", "key": ename})

    # --- Personnages historiques (from entity extraction, separate from character_bios) ---
    for entity in narrative_blocks.get("entities_personnage_historique", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", "?")
        html = format_character_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["personnages"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "character", "key": f"entity_{ename}"})

    # --- Légendes (from entity extraction) ---
    for entity in narrative_blocks.get("entities_legende", []):
        if not isinstance(entity, dict):
            continue
        ename = entity.get("name", entity.get("title", "Légende"))
        html = format_legend_page(entity)
        page = await client.create_page(chapter_id=chapter_ids["legendes"], name=ename, html=html)
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": ename, "type": "legend", "key": f"entity_{ename}"})

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
    # Pass 3: update chapter descriptions with page counts
    # ------------------------------------------------------------------
    type_to_chapter = {
        "region": "atlas", "era": "chroniques", "faction": "factions",
        "race": "races", "cosmogony": "cosmogonies", "character": "personnages",
        "tech": "tech", "legend": "legendes", "fauna": "faune",
        "flora": "flore", "bestiary": "bestiaire", "location": "lieux",
        "resource": "ressources", "organization": "organisations",
        "artifact": "artefacts", "annex": "annexes",
    }
    chapter_page_counts: dict[int, int] = {}
    for p in pages_created:
        ch_key = type_to_chapter.get(p.get("type", ""))
        if ch_key and ch_key in chapter_ids:
            ch_id = chapter_ids[ch_key]
            chapter_page_counts[ch_id] = chapter_page_counts.get(ch_id, 0) + 1

    for key, name, desc in chapter_defs:
        ch_id = chapter_ids[key]
        count = chapter_page_counts.get(ch_id, 0)
        new_desc = f"{desc} — {count} fiche{'s' if count != 1 else ''}"
        await client.update_chapter(ch_id, description=new_desc)

    logger.info("Updated chapter descriptions with page counts")

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
