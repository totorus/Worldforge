"""Content formatters — convert narrative data structures to HTML for Bookstack pages."""

from __future__ import annotations

import html as _html
from typing import Any


def _e(text: Any) -> str:
    """HTML-escape a value."""
    return _html.escape(str(text)) if text else ""


def _markdown_to_html(text: str) -> str:
    """Very lightweight Markdown-ish to HTML converter.

    Handles: paragraphs (double newline), **bold**, *italic*, and lines
    starting with ``- `` as unordered list items.  Enough for the narrative
    blocks produced by the LLM pipeline.
    """
    if not text:
        return ""

    # Split into paragraphs
    paragraphs = text.strip().split("\n\n")
    parts: list[str] = []

    for para in paragraphs:
        lines = para.strip().split("\n")

        # Check if all lines are list items
        if all(ln.strip().startswith("- ") for ln in lines if ln.strip()):
            items = "".join(
                f"<li>{_e(ln.strip()[2:])}</li>" for ln in lines if ln.strip()
            )
            parts.append(f"<ul>{items}</ul>")
            continue

        combined = " ".join(ln.strip() for ln in lines)
        # Bold / italic
        import re

        combined = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", combined)
        combined = re.sub(r"\*(.+?)\*", r"<em>\1</em>", combined)
        parts.append(f"<p>{combined}</p>")

    return "\n".join(parts)


def _kv_table(data: dict[str, Any], header: str = "Attribut") -> str:
    """Render a dict as a simple two-column HTML table."""
    rows = "".join(
        f"<tr><td><strong>{_e(k)}</strong></td><td>{_e(v)}</td></tr>"
        for k, v in data.items()
    )
    return (
        f"<table><thead><tr><th>{_e(header)}</th><th>Valeur</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


# ------------------------------------------------------------------
# Public formatters
# ------------------------------------------------------------------


def format_region_page(region_config: dict, region_sheet: dict | None = None) -> str:
    """Format a region page (from config + optional narrative sheet)."""
    parts: list[str] = []

    parts.append(f"<h2>{_e(region_config.get('name', region_config.get('id')))}</h2>")

    # Basic info
    terrain = region_config.get("terrain", "inconnu")
    habitability = region_config.get("habitability", "?")
    max_pop = region_config.get("max_population", "?")
    parts.append(
        f"<p><strong>Terrain :</strong> {_e(terrain)}<br/>"
        f"<strong>Habitabilité :</strong> {_e(habitability)}<br/>"
        f"<strong>Population max :</strong> {_e(max_pop)}</p>"
    )

    # Resources
    resources = region_config.get("resources", [])
    if resources:
        items = "".join(f"<li>{_e(r)}</li>" for r in resources)
        parts.append(f"<h3>Ressources</h3><ul>{items}</ul>")

    # Connections
    connections = region_config.get("connections", [])
    if connections:
        items = "".join(
            f"<li>{_e(c.get('target'))} (difficulté : {_e(c.get('traversal_difficulty', '?'))})</li>"
            for c in connections
        )
        parts.append(f"<h3>Connexions</h3><ul>{items}</ul>")

    # Narrative sheet
    if region_sheet:
        if region_sheet.get("description"):
            parts.append(f"<h3>Description</h3>{_markdown_to_html(region_sheet['description'])}")
        if region_sheet.get("history"):
            parts.append(f"<h3>Histoire</h3>{_markdown_to_html(region_sheet['history'])}")
        if region_sheet.get("atmosphere"):
            parts.append(f"<h3>Atmosphère</h3>{_markdown_to_html(region_sheet['atmosphere'])}")

    return "\n".join(parts)


def format_faction_page(faction_config: dict, faction_sheet: dict | None = None) -> str:
    """Format a faction page (config + optional narrative sheet)."""
    parts: list[str] = []

    name = faction_config.get("name", faction_config.get("id"))
    parts.append(f"<h2>{_e(name)}</h2>")

    gov = faction_config.get("governance", "inconnu")
    lifespan = faction_config.get("avg_lifespan", "?")
    parts.append(
        f"<p><strong>Gouvernement :</strong> {_e(gov)}<br/>"
        f"<strong>Espérance de vie :</strong> {_e(lifespan)} ans</p>"
    )

    # Cultural traits
    traits = faction_config.get("cultural_traits", [])
    if traits:
        items = "".join(f"<li>{_e(t)}</li>" for t in traits)
        parts.append(f"<h3>Traits culturels</h3><ul>{items}</ul>")

    # Attributes
    attrs = faction_config.get("attributes", {})
    if attrs:
        parts.append(f"<h3>Attributs</h3>{_kv_table(attrs)}")

    # Narrative sheet
    if faction_sheet:
        if faction_sheet.get("description"):
            parts.append(f"<h3>Description</h3>{_markdown_to_html(faction_sheet['description'])}")
        if faction_sheet.get("history"):
            parts.append(f"<h3>Histoire</h3>{_markdown_to_html(faction_sheet['history'])}")
        if faction_sheet.get("culture"):
            parts.append(f"<h3>Culture</h3>{_markdown_to_html(faction_sheet['culture'])}")
        if faction_sheet.get("notable_characters"):
            parts.append("<h3>Personnages notables</h3>")
            for char in faction_sheet["notable_characters"]:
                if isinstance(char, dict):
                    parts.append(
                        f"<p><strong>{_e(char.get('name', '?'))}</strong> — "
                        f"{_e(char.get('role', ''))}</p>"
                    )
                else:
                    parts.append(f"<p>{_e(char)}</p>")

    return "\n".join(parts)


def format_era_page(era: dict, events: list[dict] | None = None) -> str:
    """Format an era page with its major events."""
    parts: list[str] = []

    name = era.get("name", era.get("id", "Ère inconnue"))
    parts.append(f"<h2>{_e(name)}</h2>")

    start = era.get("start_year", "?")
    end = era.get("end_year", "?")
    parts.append(f"<p><strong>Période :</strong> année {_e(start)} — année {_e(end)}</p>")

    if era.get("description"):
        parts.append(f"<h3>Résumé</h3>{_markdown_to_html(era['description'])}")

    if era.get("themes"):
        items = "".join(f"<li>{_e(t)}</li>" for t in era["themes"])
        parts.append(f"<h3>Thèmes</h3><ul>{items}</ul>")

    # Events
    if events:
        parts.append("<h3>Événements majeurs</h3>")
        for ev in events:
            year = ev.get("year", "?")
            ev_name = ev.get("name", ev.get("event_id", "?"))
            parts.append(f"<h4>Année {_e(year)} — {_e(ev_name)}</h4>")
            if ev.get("description"):
                parts.append(_markdown_to_html(ev["description"]))
            involved = ev.get("involved_factions", [])
            if involved:
                items = "".join(f"<li>{_e(f)}</li>" for f in involved)
                parts.append(f"<p><em>Factions impliquées :</em></p><ul>{items}</ul>")

    return "\n".join(parts)


def format_character_page(character: dict, biography: str | None = None) -> str:
    """Format a character biography page."""
    parts: list[str] = []

    name = character.get("name", "Personnage inconnu")
    parts.append(f"<h2>{_e(name)}</h2>")

    role = character.get("role", "")
    faction = character.get("faction_id", character.get("faction", ""))
    born = character.get("birth_year", character.get("born", "?"))
    died = character.get("death_year", character.get("died", ""))

    meta_parts = [f"<strong>Rôle :</strong> {_e(role)}"]
    if faction:
        meta_parts.append(f"<strong>Faction :</strong> {_e(faction)}")
    meta_parts.append(f"<strong>Naissance :</strong> année {_e(born)}")
    if died:
        meta_parts.append(f"<strong>Décès :</strong> année {_e(died)}")
    parts.append(f"<p>{'<br/>'.join(meta_parts)}</p>")

    # Impact
    impact = character.get("impact", character.get("attribute_modifiers"))
    if impact and isinstance(impact, dict):
        parts.append(f"<h3>Impact</h3>{_kv_table(impact, header='Attribut')}")

    # Biography text
    if biography:
        parts.append(f"<h3>Biographie</h3>{_markdown_to_html(biography)}")
    elif character.get("biography"):
        parts.append(f"<h3>Biographie</h3>{_markdown_to_html(character['biography'])}")

    return "\n".join(parts)


def format_tech_page(tech: dict) -> str:
    """Format a technology / power page."""
    parts: list[str] = []

    name = tech.get("name", tech.get("id", "?"))
    parts.append(f"<h2>{_e(name)}</h2>")

    difficulty = tech.get("unlock_difficulty", "?")
    parts.append(f"<p><strong>Difficulté de découverte :</strong> {_e(difficulty)}</p>")

    prereqs = tech.get("prerequisites", [])
    if prereqs:
        items = "".join(f"<li>{_e(p)}</li>" for p in prereqs)
        parts.append(f"<h3>Prérequis</h3><ul>{items}</ul>")

    effects = tech.get("effects", {})
    if effects:
        parts.append(f"<h3>Effets</h3>{_kv_table(effects, header='Effet')}")

    if tech.get("description"):
        parts.append(f"<h3>Description</h3>{_markdown_to_html(tech['description'])}")

    return "\n".join(parts)


def format_legend_page(legend: dict) -> str:
    """Format a legend page."""
    parts: list[str] = []

    title = legend.get("title", legend.get("name", "Légende inconnue"))
    parts.append(f"<h2>{_e(title)}</h2>")

    if legend.get("era"):
        parts.append(f"<p><em>Ère : {_e(legend['era'])}</em></p>")
    if legend.get("related_factions"):
        items = "".join(f"<li>{_e(f)}</li>" for f in legend["related_factions"])
        parts.append(f"<p><strong>Factions liées :</strong></p><ul>{items}</ul>")

    text = legend.get("text", legend.get("content", ""))
    if text:
        parts.append(_markdown_to_html(text))

    return "\n".join(parts)


def format_stats_page(config: dict, timeline: dict) -> str:
    """Format the annexe / stats page summarising world configuration and simulation."""
    parts: list[str] = []

    parts.append("<h2>Résumé de la configuration</h2>")

    meta = config.get("meta", {})
    if meta:
        parts.append(_kv_table(meta, header="Paramètre"))

    # Faction count
    factions = config.get("factions", [])
    regions = config.get("geography", {}).get("regions", [])
    techs = config.get("tech_tree", {}).get("nodes", [])
    events_pool = config.get("event_pool", [])

    parts.append("<h3>Contenu</h3>")
    parts.append(
        f"<ul>"
        f"<li><strong>Factions :</strong> {len(factions)}</li>"
        f"<li><strong>Régions :</strong> {len(regions)}</li>"
        f"<li><strong>Technologies :</strong> {len(techs)}</li>"
        f"<li><strong>Événements (pool) :</strong> {len(events_pool)}</li>"
        f"</ul>"
    )

    # Timeline stats
    parts.append("<h2>Statistiques de la simulation</h2>")

    tl_events = timeline.get("events", [])
    total_events = len(tl_events)
    black_swans = sum(1 for e in tl_events if e.get("is_black_swan"))
    characters = timeline.get("characters", [])
    total_years = meta.get("simulation_years", "?")

    parts.append(
        f"<ul>"
        f"<li><strong>Durée simulée :</strong> {_e(total_years)} ans</li>"
        f"<li><strong>Événements générés :</strong> {total_events}</li>"
        f"<li><strong>Cygnes noirs :</strong> {black_swans}</li>"
        f"<li><strong>Personnages notables :</strong> {len(characters)}</li>"
        f"</ul>"
    )

    # Category breakdown
    if tl_events:
        categories: dict[str, int] = {}
        for ev in tl_events:
            cat = ev.get("category", "autre")
            categories[cat] = categories.get(cat, 0) + 1
        parts.append(f"<h3>Événements par catégorie</h3>{_kv_table(categories, header='Catégorie')}")

    return "\n".join(parts)
