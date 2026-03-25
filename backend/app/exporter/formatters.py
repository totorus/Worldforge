"""Content formatters — convert narrative data structures to HTML for Bookstack pages."""

from __future__ import annotations

import html as _html
import re
from typing import Any


# ------------------------------------------------------------------
# Scales: map 0.0–1.0 indices to human-readable labels
# ------------------------------------------------------------------

_GENERIC_SCALE = [
    (0.2, "Négligeable"),
    (0.4, "Faible"),
    (0.6, "Modéré"),
    (0.8, "Élevé"),
    (1.01, "Très élevé"),
]

_SCALES: dict[str, list[tuple[float, str]]] = {
    "habitability": [
        (0.2, "Hostile"),
        (0.4, "Rude"),
        (0.6, "Modérée"),
        (0.8, "Favorable"),
        (1.01, "Idéale"),
    ],
    "traversal_difficulty": [
        (0.2, "Triviale"),
        (0.4, "Faible"),
        (0.6, "Modérée"),
        (0.8, "Difficile"),
        (1.01, "Extrême"),
    ],
    "unlock_difficulty": [
        (0.2, "Triviale"),
        (0.4, "Faible"),
        (0.6, "Modérée"),
        (0.8, "Difficile"),
        (1.01, "Extrême"),
    ],
    "cohesion": [
        (0.2, "Fragmentée"),
        (0.4, "Fragile"),
        (0.6, "Modérée"),
        (0.8, "Solide"),
        (1.01, "Inébranlable"),
    ],
    "fertility": [
        (0.2, "Stérile"),
        (0.4, "Faible"),
        (0.6, "Modérée"),
        (0.8, "Fertile"),
        (1.01, "Très fertile"),
    ],
    "adaptability": [
        (0.2, "Rigide"),
        (0.4, "Peu adaptable"),
        (0.6, "Modérée"),
        (0.8, "Adaptable"),
        (1.01, "Très adaptable"),
    ],
    "expansionism": [
        (0.2, "Isolationniste"),
        (0.4, "Prudent"),
        (0.6, "Modéré"),
        (0.8, "Expansionniste"),
        (1.01, "Impérialiste"),
    ],
    "aggressiveness": [
        (0.2, "Pacifique"),
        (0.4, "Défensif"),
        (0.6, "Modéré"),
        (0.8, "Agressif"),
        (1.01, "Belliqueux"),
    ],
    "power_affinity": [
        (0.2, "Réfractaire"),
        (0.4, "Faible"),
        (0.6, "Modérée"),
        (0.8, "Forte"),
        (1.01, "Très forte"),
    ],
}

# Fields to display with a friendly label in wiki pages
_FIELD_LABELS: dict[str, str] = {
    "habitability": "Habitabilité",
    "traversal_difficulty": "Difficulté de traversée",
    "unlock_difficulty": "Difficulté de découverte",
    "cohesion": "Cohésion",
    "fertility": "Fertilité",
    "adaptability": "Adaptabilité",
    "expansionism": "Expansionnisme",
    "aggressiveness": "Agressivité",
    "power_affinity": "Affinité magique",
    "military": "Militaire",
    "construction": "Construction",
}


def _humanize(value: Any, field_name: str = "") -> str:
    """Convert a numeric index to a human-readable label, or pass through."""
    if not isinstance(value, (int, float)):
        return str(value) if value else ""
    # Large integers (population, lifespan) stay as numbers
    if isinstance(value, int) and value > 10:
        return f"{value:,}".replace(",", "\u202f")  # thin space separator
    if isinstance(value, float) and value > 1.0:
        return f"{value:,.1f}".replace(",", "\u202f")
    # 0.0–1.0 range: use scale
    scale = _SCALES.get(field_name, _GENERIC_SCALE)
    for threshold, label in scale:
        if value < threshold:
            return label
    return scale[-1][1]


def _label(field_name: str) -> str:
    """Get a French label for a field name."""
    return _FIELD_LABELS.get(field_name, field_name.replace("_", " ").capitalize())


def _e(text: Any) -> str:
    """HTML-escape a value."""
    return _html.escape(str(text)) if text else ""


def _markdown_to_html(text: str) -> str:
    """Very lightweight Markdown-ish to HTML converter.

    Handles: paragraphs (double newline), **bold**, *italic*, and lines
    starting with ``- `` as unordered list items.
    """
    if not text:
        return ""

    # Guard against non-string values (LLM may produce dicts/lists)
    if not isinstance(text, str):
        text = str(text)

    text = text.strip()
    paragraphs = text.split("\n\n")
    parts: list[str] = []

    for para in paragraphs:
        lines = para.strip().split("\n")

        if all(ln.strip().startswith("- ") for ln in lines if ln.strip()):
            items = "".join(
                f"<li>{_e(ln.strip()[2:])}</li>" for ln in lines if ln.strip()
            )
            parts.append(f"<ul>{items}</ul>")
            continue

        combined = " ".join(ln.strip() for ln in lines)
        combined = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", combined)
        combined = re.sub(r"\*(.+?)\*", r"<em>\1</em>", combined)
        parts.append(f"<p>{combined}</p>")

    return "\n".join(parts)


def _format_rich_item(item: Any, id_names: dict[str, str] | None = None) -> str:
    """Render a list item that may be a string, dict {name, description, ...}, or other."""
    if isinstance(item, str):
        return f"<p>{_markdown_to_html(item)}</p>"
    if isinstance(item, dict):
        name = item.get("name", item.get("title", ""))
        year = item.get("year", "")
        desc = item.get("description", item.get("narrative", item.get("text", "")))
        event_id = item.get("event_id", "")

        # Build header
        header_parts = []
        if year:
            header_parts.append(f"Année {_e(year)}")
        if name:
            header_parts.append(_e(name))
        header = " — ".join(header_parts) if header_parts else _e(event_id or "?")

        parts = [f"<h4>{header}</h4>"]
        if desc:
            parts.append(_markdown_to_html(desc))

        # Render remaining fields we haven't used
        _names = id_names or {}
        skip = {"name", "title", "year", "description", "narrative", "text", "event_id", "id"}
        for k, v in item.items():
            if k in skip:
                continue
            if isinstance(v, str) and v.strip():
                resolved = _names.get(v, v)
                parts.append(f"<p><strong>{_label(k)} :</strong> {_markdown_to_html(resolved)}</p>")
            elif isinstance(v, (int, float)):
                parts.append(f"<p><strong>{_label(k)} :</strong> {_e(_humanize(v, k))}</p>")
            elif isinstance(v, list) and v:
                items_html = "".join(
                    f"<li>{_e(_names.get(i, i) if isinstance(i, str) else str(i))}</li>" for i in v
                )
                parts.append(f"<p><strong>{_label(k)} :</strong></p><ul>{items_html}</ul>")
        return "\n".join(parts)
    return f"<p>{_e(str(item))}</p>"


def _kv_table(data: dict[str, Any], header: str = "Attribut", humanize: bool = True) -> str:
    """Render a dict as a simple two-column HTML table with humanized labels."""
    rows = ""
    for k, v in data.items():
        display_key = _label(k) if humanize else _e(k)
        display_val = _e(_humanize(v, k)) if humanize else _e(v)
        rows += f"<tr><td><strong>{display_key}</strong></td><td>{display_val}</td></tr>"
    return (
        f"<table><thead><tr><th>{_e(header)}</th><th>Valeur</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


# ------------------------------------------------------------------
# Public formatters
# ------------------------------------------------------------------


def format_region_page(region_config: dict, narrative: dict | None = None, id_names: dict[str, str] | None = None) -> str:
    """Format a region page (from config + optional narrative)."""
    parts: list[str] = []
    name = region_config.get("name", region_config.get("id"))
    parts.append(f"<h2>{_e(name)}</h2>")

    # Basic info from config
    terrain = region_config.get("terrain", "")
    habitability = region_config.get("habitability", "")
    max_pop = region_config.get("max_population", "")
    if terrain or habitability or max_pop:
        meta = []
        if terrain:
            meta.append(f"<strong>Terrain :</strong> {_e(terrain)}")
        if habitability != "":
            meta.append(f"<strong>Habitabilité :</strong> {_e(_humanize(habitability, 'habitability'))}")
        if max_pop:
            meta.append(f"<strong>Population max :</strong> {_e(_humanize(max_pop, 'max_population'))}")
        parts.append(f"<p>{'<br/>'.join(meta)}</p>")

    # Resources from config
    resources = region_config.get("resources", [])
    if resources:
        _names = id_names or {}
        items = "".join(f"<li>{_e(_names.get(r, r))}</li>" for r in resources)
        parts.append(f"<h3>Ressources</h3><ul>{items}</ul>")

    # Connections from config
    connections = region_config.get("connections", [])
    if connections:
        _names = id_names or {}
        items = ""
        for c in connections:
            target_id = c.get("target", "?")
            target_name = _names.get(target_id, target_id)
            diff = _humanize(c.get("traversal_difficulty", "?"), "traversal_difficulty")
            items += f"<li>{_e(target_name)} (difficulté : {_e(diff)})</li>"
        parts.append(f"<h3>Connexions</h3><ul>{items}</ul>")

    # Narrative enrichment — support both old and new field names
    if narrative:
        for field, title in [
            ("description", "Description"),
            ("landscape", "Paysage"),
            ("atmosphere", "Atmosphère"),
            ("history", "Histoire"),
            ("strategic_importance", "Importance stratégique"),
            ("resources_description", "Ressources"),
        ]:
            text = narrative.get(field)
            if text:
                parts.append(f"<h3>{title}</h3>{_markdown_to_html(text)}")

        notable = narrative.get("notable_events", [])
        if notable:
            parts.append("<h3>Événements notables</h3>")
            for e in notable:
                if isinstance(e, dict):
                    ename = e.get("name", e.get("id", "?"))
                    eyear = e.get("year", "")
                    edesc = e.get("description", "")
                    header = f"Année {_e(eyear)} — {_e(ename)}" if eyear else _e(ename)
                    parts.append(f"<h4>{header}</h4>")
                    if edesc:
                        parts.append(_markdown_to_html(edesc))
                else:
                    parts.append(f"<p>{_e(e)}</p>")

    return "\n".join(parts)


def format_faction_page(faction_config: dict, narrative: dict | None = None, id_names: dict[str, str] | None = None) -> str:
    """Format a faction page (config + optional narrative)."""
    parts: list[str] = []
    name = faction_config.get("name", faction_config.get("id"))
    parts.append(f"<h2>{_e(name)}</h2>")

    gov = faction_config.get("governance", "")
    lifespan = faction_config.get("avg_lifespan", "")
    if gov or lifespan:
        meta = []
        if gov:
            meta.append(f"<strong>Gouvernement :</strong> {_e(gov)}")
        if lifespan:
            meta.append(f"<strong>Espérance de vie :</strong> {_e(lifespan)} ans")
        parts.append(f"<p>{'<br/>'.join(meta)}</p>")

    traits = faction_config.get("cultural_traits", [])
    if traits:
        items = "".join(f"<li>{_e(t)}</li>" for t in traits)
        parts.append(f"<h3>Traits culturels</h3><ul>{items}</ul>")

    attrs = faction_config.get("attributes", {})
    if attrs:
        parts.append(f"<h3>Attributs</h3>{_kv_table(attrs)}")

    # Narrative enrichment
    if narrative:
        for field, title in [
            ("description", "Description"),
            ("history", "Histoire"),
            ("culture", "Culture"),
            ("governance_description", "Gouvernance"),
            ("current_state", "État actuel"),
        ]:
            text = narrative.get(field)
            if text:
                parts.append(f"<h3>{title}</h3>{_markdown_to_html(text)}")

        for list_field, title in [
            ("strengths", "Forces"),
            ("weaknesses", "Faiblesses"),
            ("notable_moments", "Moments clés"),
        ]:
            items_list = narrative.get(list_field, [])
            if items_list:
                if isinstance(items_list, list):
                    parts.append(f"<h3>{title}</h3>")
                    for i in items_list:
                        parts.append(_format_rich_item(i, id_names=id_names))
                else:
                    parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(items_list))}")

        notable_chars = narrative.get("notable_characters", [])
        if notable_chars:
            parts.append("<h3>Personnages notables</h3>")
            for char in notable_chars:
                if isinstance(char, dict):
                    parts.append(
                        f"<p><strong>{_e(char.get('name', '?'))}</strong> — "
                        f"{_e(char.get('role', ''))}</p>"
                    )
                else:
                    parts.append(f"<p>{_e(char)}</p>")

    return "\n".join(parts)


def format_era_page(
    era: dict,
    sim_events: list[dict] | None = None,
    narrative_events: list[dict] | None = None,
) -> str:
    """Format an era page with its events."""
    parts: list[str] = []
    name = era.get("name", era.get("id", "Ère inconnue"))
    parts.append(f"<h2>{_e(name)}</h2>")

    start = era.get("start_year", "?")
    end = era.get("end_year", "?")
    parts.append(f"<p><strong>Période :</strong> année {_e(start)} — année {_e(end)}</p>")

    if era.get("description"):
        parts.append(f"<h3>Résumé</h3>{_markdown_to_html(era['description'])}")

    # Themes (old format)
    if era.get("themes"):
        items = "".join(f"<li>{_e(t)}</li>" for t in era["themes"])
        parts.append(f"<h3>Thèmes</h3><ul>{items}</ul>")

    # Key events from narrative era (new format)
    key_events = era.get("key_events", [])
    if key_events:
        items = "".join(f"<li>{_e(e)}</li>" for e in key_events)
        parts.append(f"<h3>Événements clés</h3><ul>{items}</ul>")

    # Detailed narrative events
    if narrative_events:
        parts.append("<h3>Chronique détaillée</h3>")
        for ev in sorted(narrative_events, key=lambda e: e.get("year", 0)):
            year = ev.get("year", "?")
            ev_title = ev.get("title", ev.get("name", ev.get("event_id", "?")))
            parts.append(f"<h4>Année {_e(year)} — {_e(ev_title)}</h4>")
            narrative_text = ev.get("narrative", ev.get("description", ""))
            if narrative_text:
                parts.append(_markdown_to_html(narrative_text))
            consequences = ev.get("consequences_narrative", "")
            if consequences:
                parts.append(f"<p><em>Conséquences :</em> {_markdown_to_html(consequences)}</p>")
            involved = ev.get("involved_factions", [])
            if involved:
                items = "".join(f"<li>{_e(f)}</li>" for f in involved)
                parts.append(f"<p><em>Factions impliquées :</em></p><ul>{items}</ul>")

    # Simulation events (fallback if no narrative events)
    elif sim_events:
        parts.append("<h3>Événements</h3>")
        for ev in sim_events:
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

    meta_parts = []
    if role:
        meta_parts.append(f"<strong>Rôle :</strong> {_e(role)}")
    if faction:
        meta_parts.append(f"<strong>Faction :</strong> {_e(faction)}")
    race = character.get("race", "")
    if race:
        meta_parts.append(f"<strong>Race :</strong> {_e(race)}")
    meta_parts.append(f"<strong>Naissance :</strong> année {_e(born)}")
    if died:
        meta_parts.append(f"<strong>Décès :</strong> année {_e(died)}")
    statut = character.get("statut_actuel", "")
    if statut:
        meta_parts.append(f"<strong>Statut :</strong> {_e(statut)}")
    parts.append(f"<p>{'<br/>'.join(meta_parts)}</p>")

    # Physical description
    description_physique = character.get("description_physique", "")
    if description_physique:
        parts.append(f"<h3>Description physique</h3>{_markdown_to_html(description_physique)}")

    # Personality
    personality = character.get("personality", "")
    if personality:
        parts.append(f"<h3>Personnalité</h3>{_markdown_to_html(personality)}")

    # Impact (old format: dict)
    impact = character.get("impact", character.get("attribute_modifiers"))
    if impact and isinstance(impact, dict):
        parts.append(f"<h3>Impact</h3>{_kv_table(impact, header='Attribut')}")

    # Biography — from argument, from character dict, or from 'legacy'
    bio = biography or character.get("biography", "")
    if bio:
        parts.append(f"<h3>Biographie</h3>{_markdown_to_html(bio)}")

    legacy = character.get("legacy", "")
    if legacy:
        parts.append(f"<h3>Héritage</h3>{_markdown_to_html(legacy)}")

    return "\n".join(parts)


def format_tech_page(tech: dict) -> str:
    """Format a technology / power page."""
    parts: list[str] = []
    name = tech.get("name", tech.get("id", "?"))
    parts.append(f"<h2>{_e(name)}</h2>")

    difficulty = tech.get("unlock_difficulty", "")
    if difficulty != "":
        parts.append(f"<p><strong>Difficulté de découverte :</strong> {_e(_humanize(difficulty, 'unlock_difficulty'))}</p>")

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

    legend_type = legend.get("type", "")
    if legend_type:
        parts.append(f"<p><em>Type : {_e(legend_type)}</em></p>")

    era = legend.get("era", legend.get("era_origin", ""))
    if era:
        parts.append(f"<p><em>Ère : {_e(era)}</em></p>")

    related_factions = legend.get("related_factions", [])
    if related_factions:
        items = "".join(f"<li>{_e(f)}</li>" for f in related_factions)
        parts.append(f"<p><strong>Factions liées :</strong></p><ul>{items}</ul>")

    related_chars = legend.get("related_characters", [])
    if related_chars:
        items = "".join(f"<li>{_e(c)}</li>" for c in related_chars)
        parts.append(f"<p><strong>Personnages liés :</strong></p><ul>{items}</ul>")

    # Narrative text
    text = legend.get("narrative", legend.get("text", legend.get("content", "")))
    if text:
        parts.append(_markdown_to_html(text))

    moral = legend.get("moral", "")
    if moral:
        parts.append(f"<blockquote><em>{_markdown_to_html(moral)}</em></blockquote>")

    return "\n".join(parts)


def format_race_page(race: dict) -> str:
    """Format a race/people page."""
    parts: list[str] = []
    name = race.get("name", "Peuple inconnu")
    parts.append(f"<h2>{_e(name)}</h2>")

    if race.get("description_physique"):
        parts.append(f"<h3>Description physique</h3>{_markdown_to_html(race['description_physique'])}")
    if race.get("esperance_de_vie"):
        parts.append(f"<p><strong>Espérance de vie :</strong> {_e(race['esperance_de_vie'])}</p>")
    if race.get("philosophie"):
        parts.append(f"<h3>Philosophie & Valeurs</h3>{_markdown_to_html(race['philosophie'])}")
    if race.get("rapport_magie"):
        parts.append(f"<h3>Rapport à la magie</h3>{_markdown_to_html(race['rapport_magie'])}")
    if race.get("rapport_technologie"):
        parts.append(f"<h3>Rapport à la technologie</h3>{_markdown_to_html(race['rapport_technologie'])}")

    factions = race.get("factions_associees", [])
    if factions:
        items = "".join(f"<li>{_e(f)}</li>" for f in factions) if isinstance(factions, list) else f"<li>{_e(factions)}</li>"
        parts.append(f"<h3>Factions associées</h3><ul>{items}</ul>")

    regions = race.get("regions_habitat", [])
    if regions:
        items = "".join(f"<li>{_e(r)}</li>" for r in regions) if isinstance(regions, list) else f"<li>{_e(regions)}</li>"
        parts.append(f"<h3>Régions d'habitat</h3><ul>{items}</ul>")

    relations = race.get("relations_inter_races", "")
    if relations:
        if isinstance(relations, str):
            parts.append(f"<h3>Relations inter-races</h3>{_markdown_to_html(relations)}")
        elif isinstance(relations, list):
            items = "".join(f"<li>{_e(r)}</li>" for r in relations)
            parts.append(f"<h3>Relations inter-races</h3><ul>{items}</ul>")

    traits = race.get("traits_culturels", "")
    if traits:
        if isinstance(traits, str):
            parts.append(f"<h3>Traits culturels</h3>{_markdown_to_html(traits)}")
        elif isinstance(traits, list):
            items = "".join(f"<li>{_e(t)}</li>" for t in traits)
            parts.append(f"<h3>Traits culturels</h3><ul>{items}</ul>")

    return "\n".join(parts)


def format_cosmogony_page(cosmo: dict) -> str:
    """Format a cosmogony page."""
    parts: list[str] = []
    title = cosmo.get("name", "Cosmogonie inconnue")
    parts.append(f"<h2>{_e(title)}</h2>")
    parts.append(f"<p><em>Peuple : {_e(cosmo.get('race', '?'))}</em></p>")

    if cosmo.get("creation_du_monde"):
        parts.append(f"<h3>Création du monde</h3>{_markdown_to_html(cosmo['creation_du_monde'])}")

    divinites = cosmo.get("divinites", [])
    if divinites:
        items = "".join(f"<li>{_e(d) if isinstance(d, str) else _e(d.get('name', '?'))}</li>" for d in divinites)
        parts.append(f"<h3>Divinités & Forces primordiales</h3><ul>{items}</ul>")

    if cosmo.get("naissance_du_peuple"):
        parts.append(f"<h3>Naissance du peuple</h3>{_markdown_to_html(cosmo['naissance_du_peuple'])}")
    if cosmo.get("valeurs_fondatrices"):
        parts.append(f"<h3>Valeurs fondatrices</h3>{_markdown_to_html(cosmo['valeurs_fondatrices'])}")
    if cosmo.get("recit_complet"):
        parts.append(f"<h3>Récit mythique</h3>{_markdown_to_html(cosmo['recit_complet'])}")

    return "\n".join(parts)


def format_fauna_page(entity: dict) -> str:
    """Format a fauna page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("habitat", "Habitat"),
                          ("comportement", "Comportement"), ("dangerosite", "Dangerosité"),
                          ("lien_magie", "Lien à la magie"), ("rarete", "Rareté")]:
        if entity.get(field):
            parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(entity[field]))}")
    return "\n".join(parts)


def format_flora_page(entity: dict) -> str:
    """Format a flora page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("habitat", "Habitat"),
                          ("proprietes", "Propriétés"), ("usages", "Usages"),
                          ("rarete", "Rareté")]:
        if entity.get(field):
            parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(entity[field]))}")
    return "\n".join(parts)


def format_bestiary_page(entity: dict) -> str:
    """Format a bestiary page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("habitat", "Habitat"),
                          ("pouvoirs", "Pouvoirs & Capacités"), ("dangerosite", "Dangerosité"),
                          ("origine", "Origine"), ("faiblesses", "Faiblesses")]:
        val = entity.get(field)
        if val:
            if isinstance(val, list):
                items = "".join(f"<li>{_e(v)}</li>" for v in val)
                parts.append(f"<h3>{title}</h3><ul>{items}</ul>")
            else:
                parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(val))}")
    legendes = entity.get("legendes_associees", [])
    if legendes:
        if isinstance(legendes, list):
            items = "".join(f"<li>{_e(l)}</li>" for l in legendes)
            parts.append(f"<h3>Légendes associées</h3><ul>{items}</ul>")
        else:
            parts.append(f"<h3>Légendes associées</h3>{_markdown_to_html(str(legendes))}")
    return "\n".join(parts)


def format_notable_location_page(entity: dict) -> str:
    """Format a notable location page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")

    statut = entity.get("statut", "")
    region = entity.get("region", "")
    meta = []
    if statut:
        meta.append(f"<strong>Statut :</strong> {_e(statut)}")
    if region:
        meta.append(f"<strong>Région :</strong> {_e(region)}")
    if meta:
        parts.append(f"<p>{'<br/>'.join(meta)}</p>")

    for field, title in [("description", "Description"), ("histoire", "Histoire"),
                          ("importance", "Importance")]:
        if entity.get(field):
            parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(entity[field]))}")
    return "\n".join(parts)


def format_resource_page(entity: dict) -> str:
    """Format a resource page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("rarete", "Rareté"),
                          ("proprietes", "Propriétés"), ("localisation", "Localisation"),
                          ("usages", "Usages")]:
        if entity.get(field):
            parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(entity[field]))}")
    return "\n".join(parts)


def format_organization_page(entity: dict) -> str:
    """Format an organization page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("fondation", "Fondation"),
                          ("objectifs", "Objectifs"), ("structure", "Structure"),
                          ("influence", "Influence")]:
        if entity.get(field):
            parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(entity[field]))}")
    membres = entity.get("membres_notables", [])
    if membres:
        if isinstance(membres, list):
            items = "".join(f"<li>{_e(m)}</li>" for m in membres)
            parts.append(f"<h3>Membres notables</h3><ul>{items}</ul>")
        else:
            parts.append(f"<h3>Membres notables</h3>{_markdown_to_html(str(membres))}")
    return "\n".join(parts)


def format_artifact_page(entity: dict) -> str:
    """Format an artifact page."""
    parts: list[str] = []
    parts.append(f"<h2>{_e(entity.get('name', '?'))}</h2>")
    for field, title in [("description", "Description"), ("origine", "Origine"),
                          ("pouvoirs", "Pouvoirs & Propriétés"),
                          ("localisation", "Localisation"), ("histoire", "Histoire")]:
        val = entity.get(field)
        if val:
            if isinstance(val, list):
                items = "".join(f"<li>{_e(v)}</li>" for v in val)
                parts.append(f"<h3>{title}</h3><ul>{items}</ul>")
            else:
                parts.append(f"<h3>{title}</h3>{_markdown_to_html(str(val))}")
    return "\n".join(parts)


def format_stats_page(config: dict, timeline: dict) -> str:
    """Format the annexe / stats page."""
    parts: list[str] = []

    parts.append("<h2>Résumé de la configuration</h2>")

    meta = config.get("meta", {})
    if meta:
        parts.append(_kv_table(meta, header="Paramètre"))

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

    if tl_events:
        categories: dict[str, int] = {}
        for ev in tl_events:
            cat = ev.get("category", "autre")
            categories[cat] = categories.get(cat, 0) + 1
        parts.append(f"<h3>Événements par catégorie</h3>{_kv_table(categories, header='Catégorie')}")

    return "\n".join(parts)
