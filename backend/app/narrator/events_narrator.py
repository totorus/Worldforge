from app.narrator.json_utils import extract_json, unwrap_llm_json
"""Event narratives — generates narrative descriptions for significant events."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.events")


def _group_events_by_era(events: list, eras: list) -> dict[str, list]:
    """Group events into their corresponding eras."""
    grouped: dict[str, list] = {era["name"]: [] for era in eras}

    for evt in events:
        year = evt.get("year", 0)
        placed = False
        for era in eras:
            if era["start_year"] <= year <= era["end_year"]:
                grouped[era["name"]].append(evt)
                placed = True
                break
        if not placed and eras:
            # Place in closest era
            grouped[eras[-1]["name"]].append(evt)

    return grouped


def _select_significant_events(events: list, max_per_era: int = 10) -> list:
    """Select the most significant events, prioritizing black swans and conflicts."""
    # Sort by significance: black swans first, then by category importance
    priority = {"catastrophe": 4, "conflict": 3, "discovery": 2, "diplomacy": 1, "internal": 1, "migration": 0}

    scored = []
    for evt in events:
        evt_id = evt.get("event_id", "")
        is_black_swan = evt_id.startswith("bsw_")
        cat_score = priority.get(evt.get("category", ""), 0)
        score = (10 if is_black_swan else 0) + cat_score
        scored.append((score, evt))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [evt for _, evt in scored[:max_per_era]]


async def narrate_events(events: list, config: dict, eras: list, *, registry=None) -> list[dict]:
    """Generate narrative descriptions for significant events, grouped by era.

    Args:
        events: Flat list of event dicts from timeline (with year, event_id, etc.).
        config: World configuration.
        eras: List of era dicts from era splitting.

    Returns:
        List of narrated event dicts with keys: year, event_id, era, title,
        narrative, involved_factions, consequences_narrative
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")
    factions = {f["id"]: f["name"] for f in config.get("factions", [])}
    regions = {r["id"]: r["name"] for r in config.get("geography", {}).get("regions", [])}

    grouped = _group_events_by_era(events, eras)
    narrated_events = []

    for era in eras:
        era_name = era["name"]
        era_events = grouped.get(era_name, [])
        significant = _select_significant_events(era_events)

        if not significant:
            continue

        # Build event descriptions for the LLM
        events_desc = []
        for evt in significant:
            involved = [factions.get(f, f) for f in evt.get("involved_factions", [])]
            in_regions = [regions.get(r, r) for r in evt.get("involved_regions", [])]
            events_desc.append({
                "year": evt.get("year"),
                "event_id": evt.get("event_id"),
                "involved_factions": involved,
                "involved_regions": in_regions,
                "outcome": evt.get("outcome", {}),
            })

        # Build registry context if available
        registry_context = ""
        if registry:
            summary = registry.compact_summary(max_chars=400)
            if summary:
                registry_context = (
                    f"\n\nEntités connues du monde (utilise ces noms, tu peux en introduire de nouveaux si le récit le justifie) :\n{summary}"
                )

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un chroniqueur et conteur spécialisé dans la narration historique de mondes fictifs. "
                    "Tu écris toujours en français avec un style littéraire évocateur. "
                    f"Le monde « {world_name} » est de genre « {genre} ». "
                    "Tu dois transformer des données brutes d'événements en récits captivants. "
                    f"Réponds uniquement avec un JSON valide (sans markdown, sans commentaire).{registry_context}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Nous sommes dans l'ère « {era_name} » "
                    f"(an {era.get('start_year', '?')} à {era.get('end_year', '?')}) : "
                    f"{era.get('description', '')}\n\n"
                    "CONTRAINTE : tous les événements de cette ère doivent être cohérents "
                    "avec le ton et le contexte de l'ère. Ne mentionne pas d'événements "
                    "ou personnages d'autres ères sans justification narrative.\n\n"
                    f"Voici les événements marquants :\n{json.dumps(events_desc, ensure_ascii=False, indent=2)}\n\n"
                    "Pour chaque événement, génère :\n"
                    "- year : année (DOIT être entre "
                    f"{era.get('start_year', '?')} et {era.get('end_year', '?')})\n"
                    "- event_id : identifiant original\n"
                    "- era : nom de l'ère\n"
                    "- title : titre dramatique de l'événement (en français)\n"
                    "- narrative : récit de l'événement (3-5 phrases, style littéraire)\n"
                    "- involved_factions : noms des factions impliquées (STRINGS, pas d'objets)\n"
                    "- consequences_narrative : conséquences narratives (1-2 phrases)\n\n"
                    "Réponds avec une liste JSON."
                ),
            },
        ]

        logger.info("Narrating %d events for era '%s'", len(significant), era_name)
        response = await llm_router.complete(
            task="event_narrative", messages=messages, temperature=0.8, max_tokens=4096
        )

        try:
            era_narrated = extract_json(response)
            era_narrated = unwrap_llm_json(era_narrated, expect_list=True)
            if isinstance(era_narrated, list):
                # Normalize involved_factions: LLM sometimes returns dicts or comma-separated strings
                for evt in era_narrated:
                    if isinstance(evt, dict) and "involved_factions" in evt:
                        evt_factions = evt["involved_factions"]
                        if isinstance(evt_factions, str):
                            # Split comma-separated string into list
                            evt["involved_factions"] = [f.strip() for f in evt_factions.split(",") if f.strip()]
                        elif isinstance(evt_factions, list):
                            evt["involved_factions"] = [
                                f.get("name", str(f)) if isinstance(f, dict) else str(f)
                                for f in evt_factions
                            ]
                narrated_events.extend(era_narrated)
            else:
                logger.warning("Expected list for era '%s', got %s", era_name, type(era_narrated))
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse event narratives for era '%s': %s", era_name, e)
            # Fallback: create minimal entries
            for evt in significant:
                narrated_events.append({
                    "year": evt.get("year"),
                    "event_id": evt.get("event_id"),
                    "era": era_name,
                    "title": evt.get("event_id", "Événement"),
                    "narrative": "",
                    "involved_factions": evt.get("involved_factions", []),
                    "consequences_narrative": "",
                })

    return narrated_events
