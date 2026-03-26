# app/narrator/entity_extraction.py
"""Entity extraction — detects and generates sheets for invented entities in narrative blocks."""

import json
import logging
from app.narrator.json_utils import extract_json, unwrap_llm_json
from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.entities")

ENTITY_TYPES = [
    "race", "creature", "faune", "flore", "bestiaire",
    "lieu_notable", "ressource", "organisation", "artefact",
    "personnage_historique", "legende",
]

# Fields expected per entity type
ENTITY_TEMPLATES = {
    "race": {
        "fields": "name, description_physique, esperance_de_vie, factions_associees, regions_habitat, philosophie, rapport_magie, rapport_technologie, relations_inter_races, traits_culturels",
        "description": "Un peuple ou une race unique au monde (pas les humains génériques sauf s'ils ont des particularités)"
    },
    "creature": {
        "fields": "name, description, habitat, comportement, dangerosite, pouvoirs, origine, rarete",
        "description": "Créature unique ou espèce inventée, distincte de la faune ordinaire et du bestiaire mythique"
    },
    "faune": {
        "fields": "name, description, habitat, comportement, dangerosite, lien_magie, rarete",
        "description": "Animal spécifique au monde : mutation, usage alchimique, rôle narratif. Pas les animaux génériques."
    },
    "flore": {
        "fields": "name, description, habitat, proprietes, usages, rarete",
        "description": "Plante spécifique au monde : magique, mutée, rôle narratif. Pas les plantes génériques."
    },
    "bestiaire": {
        "fields": "name, description, habitat, pouvoirs, dangerosite, origine, faiblesses, legendes_associees",
        "description": "Créature magique (dragon, manticore...) ou être unique (un monstre nommé)"
    },
    "lieu_notable": {
        "fields": "name, description, region, histoire, importance, statut (existant/ruines/légendaire/localisation_perdue/disparu)",
        "description": "Lieu inventé unique : bibliothèque, temple, forteresse, forêt maudite..."
    },
    "ressource": {
        "fields": "name, description, rarete, proprietes, localisation, usages",
        "description": "Ressource inventée unique : minerai magique, essence rare..."
    },
    "organisation": {
        "fields": "name, description, fondation, objectifs, structure, membres_notables, influence",
        "description": "Ordre, guilde, secte, culte, confrérie nommée"
    },
    "artefact": {
        "fields": "name, description, origine, pouvoirs, localisation, histoire",
        "description": "Objet unique et nommé : épée légendaire, relique, grimoire..."
    },
    "personnage_historique": {
        "fields": "name, description_physique, biographie, role, faction, race, epoque, naissance, mort, statut_actuel (vivant/mort/disparu/inconnu), faits_marquants, heritage",
        "description": "Personnage nommé ayant un impact historique. Pas les figurants ou soldats anonymes."
    },
    "legende": {
        "fields": "name, recit, type (cosmogonie/prophétie/conte_moral/épopée/mythe), peuples_rattaches, portee (unique/partagee), variantes_par_peuple (si partagée)",
        "description": "Mythe, légende ou récit fondateur mentionné dans le lore"
    },
}


def _build_known_entities(config: dict, narrative_blocks: dict) -> list[str]:
    """Build list of entity names that already have sheets."""
    known = []

    # Factions from config
    for f in config.get("factions", []):
        known.append(f.get("name", ""))

    # Regions from config
    for r in config.get("geography", {}).get("regions", []):
        known.append(r.get("name", ""))

    # Characters from narrative
    for c in narrative_blocks.get("characters", []):
        if isinstance(c, dict):
            known.append(c.get("name", ""))

    # Techs from config
    for t in config.get("tech_tree", {}).get("nodes", []):
        known.append(t.get("name", ""))

    # Previously extracted entities
    for entity_type in ENTITY_TYPES:
        for e in narrative_blocks.get(f"entities_{entity_type}", []):
            if isinstance(e, dict):
                known.append(e.get("name", ""))

    return [n for n in known if n]


def _collect_narrative_text(narrative_blocks: dict) -> str:
    """Concatenate all narrative text from blocks for entity scanning."""
    parts = []

    for block_key in ["factions", "regions", "events", "characters", "legends"]:
        items = narrative_blocks.get(block_key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and len(v) > 20:
                            parts.append(v)

    # Also scan entity sheets from previous depth levels
    for entity_type in ENTITY_TYPES:
        items = narrative_blocks.get(f"entities_{entity_type}", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and len(v) > 20:
                            parts.append(v)

    return "\n\n".join(parts)


def _collect_era_narrative_text(narrative_blocks: dict, era: dict) -> str:
    """Collect narrative text for a specific era."""
    era_name = era.get("name", "")
    start_year = era.get("start_year", 0)
    end_year = era.get("end_year", float("inf"))
    parts = []

    # Era narrative itself
    for field in ["narrative", "description", "summary"]:
        val = era.get(field)
        if isinstance(val, str) and len(val) > 20:
            parts.append(val)

    # Events matching this era (by era field or year)
    for ev in narrative_blocks.get("events", []):
        if not isinstance(ev, dict):
            continue
        ev_era = ev.get("era", "")
        ev_year = ev.get("year")
        match = (
            ev_era == era_name
            or era_name.lower() in ev_era.lower()
            or ev_era.lower() in era_name.lower()
            or (ev_year is not None and start_year <= ev_year <= end_year)
        )
        if match:
            for v in ev.values():
                if isinstance(v, str) and len(v) > 20:
                    parts.append(v)

    if not parts:
        for block_key in ["factions", "regions"]:
            items = narrative_blocks.get(block_key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str) and len(v) > 20:
                                parts.append(v)

    return "\n\n".join(parts)


def _build_era_structured_context(timeline: dict, era: dict) -> str:
    """Build structured context from timeline data for an era."""
    start_year = era.get("start_year", 0)
    end_year = era.get("end_year", float("inf"))
    ticks = timeline.get("ticks", [])
    parts = []

    era_factions = set()
    era_regions = set()
    era_techs = set()
    era_events = []

    for tick in ticks:
        year = tick.get("year", 0)
        if not (start_year <= year <= end_year):
            continue
        for fac in tick.get("world_state", {}).get("factions", []):
            era_factions.add(fac.get("name", fac.get("id", "")))
            for tech_id in fac.get("unlocked_techs", []):
                era_techs.add(tech_id)
        for ev in tick.get("events", []):
            for r in ev.get("involved_regions", []):
                era_regions.add(r)
            era_events.append(ev.get("event_id", ""))

    if era_factions:
        parts.append(f"Factions actives : {', '.join(sorted(era_factions))}")
    if era_regions:
        parts.append(f"Régions concernées : {', '.join(sorted(era_regions))}")
    if era_techs:
        parts.append(f"Technologies déverrouillées : {', '.join(sorted(era_techs))}")
    if era_events:
        parts.append(f"Événements : {', '.join(e for e in era_events if e)}")

    return "\n".join(parts)


async def detect_entities(
    narrative_blocks: dict,
    config: dict,
    *,
    era_text: str | None = None,
    structured_context: str = "",
    previously_detected: list[str] | None = None,
    volume_hint: str = "",
) -> list[dict]:
    """Detect invented entities mentioned in narrative blocks that lack their own sheet.

    Returns list of dicts: [{name, type, context}]
    """
    known = _build_known_entities(config, narrative_blocks)
    if previously_detected:
        known.extend(previously_detected)
    text = era_text if era_text is not None else _collect_narrative_text(narrative_blocks)

    if not text:
        return []

    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Prepend structured context if provided
    if structured_context:
        text = structured_context + "\n\n" + text

    # Truncate text to fit context window
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texte tronqué...]"

    type_descriptions = "\n".join(
        f"- {t}: {info['description']}" for t, info in ENTITY_TEMPLATES.items()
    )

    volume_hint_line = f"\nINDICATION DE VOLUME : {volume_hint}" if volume_hint else ""

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un analyste de lore spécialisé dans les mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Ta tâche est d'identifier les entités inventées nommées dans le texte "
                "qui n'ont pas encore de fiche dédiée. "
                "Sois EXHAUSTIF : cherche toutes les mentions de noms propres, de lieux, de créatures, de ressources, d'organisations, d'artefacts. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyse le texte narratif suivant et identifie toutes les entités inventées "
                "nommées qui mériteraient leur propre fiche encyclopédique.\n\n"
                f"Entités qui ont DÉJÀ une fiche (ne pas les inclure) :\n{', '.join(known)}\n\n"
                f"Types d'entités à détecter :\n{type_descriptions}\n\n"
                "RÈGLES :\n"
                "- Inclure : tout nom propre inventé unique au monde (créature, lieu, personnage historique, artefact...)\n"
                "- Exclure : entités génériques (marguerite, loup, hibou, taverne, soldat anonyme)\n"
                "- Exclure : les figurants sans importance historique\n"
                f"- Un personnage historique doit avoir un impact fort sur l'histoire pour mériter une fiche{volume_hint_line}\n\n"
                f"Texte narratif :\n{text}\n\n"
                "Réponds avec une liste JSON. Chaque item :\n"
                "- name : nom exact tel qu'il apparaît dans le texte\n"
                "- type : un des types listés ci-dessus\n"
                "- context : phrase courte expliquant pourquoi cette entité mérite une fiche\n"
            ),
        },
    ]

    logger.info("Detecting entities for world '%s' (known: %d)", world_name, len(known))
    response = await llm_router.complete(
        task="entity_detection", messages=messages, temperature=0.3, max_tokens=4096
    )

    try:
        entities = extract_json(response)
        entities = unwrap_llm_json(entities, expect_list=True)
        if not isinstance(entities, list):
            raise ValueError("Expected a JSON list")
        # Filter out any that are already known
        known_lower = {n.lower() for n in known}
        filtered = [
            e for e in entities
            if isinstance(e, dict)
            and e.get("name", "").lower() not in known_lower
            and e.get("type") in ENTITY_TYPES
        ]
        # Cap to avoid runaway extraction (each entity = 1 LLM call)
        MAX_ENTITIES_PER_DETECTION = 5
        if len(filtered) > MAX_ENTITIES_PER_DETECTION:
            logger.info("Capping entities from %d to %d", len(filtered), MAX_ENTITIES_PER_DETECTION)
            filtered = filtered[:MAX_ENTITIES_PER_DETECTION]
        logger.info("Detected %d new entities (from %d candidates)", len(filtered), len(entities))
        return filtered
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse entity detection JSON: %s", e)
        return []


async def generate_entity_sheet(
    entity: dict,
    config: dict,
    narrative_blocks: dict,
) -> dict:
    """Generate a detailed sheet for a detected entity.

    Args:
        entity: Dict with name, type, context.
        config: World configuration.
        narrative_blocks: Current narrative blocks for context.

    Returns:
        Sheet dict with type-specific fields.
    """
    entity_name = entity.get("name", "?")
    entity_type = entity.get("type", "entity_sheet")
    entity_context = entity.get("context", "")
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    template = ENTITY_TEMPLATES.get(entity_type, ENTITY_TEMPLATES.get("artefact"))
    fields = template["fields"]

    # Build lore context (abbreviated)
    context_parts = []
    for fac in narrative_blocks.get("factions", [])[:5]:
        if isinstance(fac, dict):
            context_parts.append(f"Faction: {fac.get('name', '?')} — {str(fac.get('description', ''))[:100]}")
    for reg in narrative_blocks.get("regions", [])[:5]:
        if isinstance(reg, dict):
            context_parts.append(f"Région: {reg.get('name', '?')} — {str(reg.get('description', ''))[:100]}")
    lore_context = "\n".join(context_parts) if context_parts else "Contexte non disponible."

    # Map entity type to LLM task
    task_map = {
        "race": "race_sheet",
        "faune": "fauna_sheet",
        "flore": "flora_sheet",
        "bestiaire": "bestiary_sheet",
        "lieu_notable": "location_sheet",
        "ressource": "resource_sheet",
        "organisation": "organization_sheet",
        "artefact": "artifact_sheet",
        "personnage_historique": "entity_sheet",
        "legende": "entity_sheet",
    }
    llm_task = task_map.get(entity_type, "entity_sheet")

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un encyclopédiste et conteur spécialisé dans les mondes fictifs. "
                "Tu écris toujours en français avec un style littéraire riche. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Tu dois créer une fiche encyclopédique CONCISE mais immersive. "
                "IMPORTANT : ta réponse doit faire MOINS de 1500 caractères au total. "
                "Chaque champ texte doit faire 1 à 3 phrases maximum. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Crée une fiche encyclopédique pour : « {entity_name} »\n"
                f"Type : {entity_type}\n"
                f"Contexte : {entity_context}\n\n"
                f"Lore du monde :\n{lore_context}\n\n"
                f"Génère un JSON avec les champs suivants : {fields}\n\n"
                "Le contenu doit être cohérent avec le lore existant et immersif. "
                "IMPORTANT : sois CONCIS. Chaque champ texte = 1 à 3 phrases max. "
                "Réponse totale < 1500 caractères."
            ),
        },
    ]

    logger.info("Generating sheet for entity '%s' (type=%s)", entity_name, entity_type)
    response = await llm_router.complete(
        task=llm_task, messages=messages, temperature=0.8, max_tokens=2048
    )

    try:
        sheet = extract_json(response)
        sheet = unwrap_llm_json(sheet, expect_dict=True)
        # If still a list, take first dict element
        if isinstance(sheet, list):
            dicts = [x for x in sheet if isinstance(x, dict)]
            if dicts:
                sheet = dicts[0]
            else:
                raise ValueError("Expected a JSON object, got list with no dicts")
        if not isinstance(sheet, dict):
            raise ValueError(f"Expected a JSON object, got {type(sheet).__name__}")
        # Flatten nested "name" field (LLM sometimes returns {"name": {"nom_complet": ...}})
        if isinstance(sheet.get("name"), dict):
            name_dict = sheet["name"]
            sheet["name"] = name_dict.get("nom_complet", name_dict.get("name", entity_name))
        sheet["name"] = entity_name
        sheet["entity_type"] = entity_type
        return sheet
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse entity sheet JSON for '%s': %s", entity_name, e)
        return {
            "name": entity_name,
            "entity_type": entity_type,
            "description": f"{entity_name} est un élément notable de {world_name}.",
        }


async def generate_cosmogony(
    race: dict,
    config: dict,
    narrative_blocks: dict,
) -> dict:
    """Generate a cosmogony for a detected race."""
    race_name = race.get("name", "?")
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Get other race names for inter-race references
    other_races = [
        r.get("name", "") for r in narrative_blocks.get("entities_race", [])
        if isinstance(r, dict) and r.get("name") != race_name
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un mythologue et conteur spécialisé dans les cosmogonies de mondes fictifs. "
                "Tu écris toujours en français avec un style épique et poétique. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Crée la cosmogonie du peuple « {race_name} ».\n\n"
                f"Description du peuple :\n{json.dumps(race, ensure_ascii=False, indent=2)}\n\n"
                f"Autres peuples connus : {', '.join(other_races) if other_races else 'aucun'}\n\n"
                "Génère un JSON avec :\n"
                "- name : titre de la cosmogonie (ex: 'La Genèse selon les Elfes des Cendres')\n"
                "- race : nom du peuple\n"
                "- creation_du_monde : récit de la création du monde selon ce peuple (5-8 phrases)\n"
                "- divinites : liste des divinités ou forces primordiales\n"
                "- naissance_du_peuple : comment ce peuple est né selon leur mythe (3-5 phrases)\n"
                "- valeurs_fondatrices : les valeurs tirées de ce mythe (2-3 phrases)\n"
                "- recit_complet : le récit mythique complet en style épique (10-15 phrases)\n"
            ),
        },
    ]

    logger.info("Generating cosmogony for race '%s'", race_name)
    response = await llm_router.complete(
        task="cosmogony", messages=messages, temperature=0.9, max_tokens=4096
    )

    try:
        cosmo = extract_json(response)
        cosmo = unwrap_llm_json(cosmo, expect_dict=True)
        if not isinstance(cosmo, dict):
            raise ValueError("Expected a JSON object")
        cosmo["race"] = race_name
        cosmo["entity_type"] = "cosmogonie"
        return cosmo
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse cosmogony JSON for '%s': %s", race_name, e)
        return {
            "name": f"Cosmogonie de {race_name}",
            "race": race_name,
            "entity_type": "cosmogonie",
            "creation_du_monde": "",
            "divinites": [],
            "naissance_du_peuple": "",
            "valeurs_fondatrices": "",
            "recit_complet": f"Les origines de {race_name} se perdent dans la nuit des temps...",
        }


async def _run_entity_extraction_iterative(
    config: dict,
    narrative_blocks: dict,
    max_depth: int = 4,
    on_progress=None,
) -> dict:
    """Run full entity extraction with iterative deepening (fallback).

    Modifies narrative_blocks in-place, adding entities_<type> keys.

    Args:
        config: World configuration.
        narrative_blocks: Current narrative blocks (modified in place).
        max_depth: Maximum depth iterations.
        on_progress: Optional async callback(message: str).

    Returns:
        Summary dict with counts per type and depth reached.
    """
    total_generated = 0

    for depth in range(1, max_depth + 1):
        if on_progress:
            await on_progress(f"Extraction d'entités — niveau {depth}/{max_depth}")

        logger.info("Entity extraction depth %d/%d", depth, max_depth)

        # Detect new entities
        new_entities = await detect_entities(narrative_blocks, config)

        if not new_entities:
            logger.info("No new entities found at depth %d, stopping", depth)
            break

        logger.info("Found %d new entities at depth %d", len(new_entities), depth)

        # Generate sheets for each entity (sequential — Kimi detection was already done)
        failed_sheets = []
        for entity in new_entities:
            try:
                sheet = await generate_entity_sheet(entity, config, narrative_blocks)
                entity_type = entity.get("type", "artefact")
                block_key = f"entities_{entity_type}"
                if block_key not in narrative_blocks:
                    narrative_blocks[block_key] = []
                narrative_blocks[block_key].append(sheet)
                total_generated += 1
            except Exception as e:
                entity_name = entity.get("name", "?")
                logger.error("Failed to generate sheet for '%s': %s: %s", entity_name, type(e).__name__, e)
                failed_sheets.append({"name": entity_name, "type": entity.get("type"), "error": str(e)[:200]})

        if failed_sheets:
            logger.warning("Entity sheet failures at depth %d: %d/%d failed", depth, len(failed_sheets), len(new_entities))

        # Generate cosmogonies for newly detected races
        races = narrative_blocks.get("entities_race", [])
        existing_cosmogonies = {
            c.get("race", "") for c in narrative_blocks.get("entities_cosmogonie", [])
            if isinstance(c, dict)
        }
        new_races = [r for r in races if isinstance(r, dict) and r.get("name", "") not in existing_cosmogonies]

        if new_races:
            if on_progress:
                await on_progress(f"Génération des cosmogonies ({len(new_races)} races)")
            for race in new_races:
                try:
                    cosmo = await generate_cosmogony(race, config, narrative_blocks)
                    if "entities_cosmogonie" not in narrative_blocks:
                        narrative_blocks["entities_cosmogonie"] = []
                    narrative_blocks["entities_cosmogonie"].append(cosmo)
                    total_generated += 1
                except Exception as e:
                    logger.error("Failed to generate cosmogony for '%s': %s", race.get("name", "?"), e)

    summary = {
        "total_generated": total_generated,
        "depth_reached": min(depth, max_depth) if total_generated > 0 else 0,
        "counts": {},
    }
    for entity_type in ENTITY_TYPES + ["cosmogonie"]:
        key = f"entities_{entity_type}"
        count = len(narrative_blocks.get(key, []))
        if count > 0:
            summary["counts"][entity_type] = count

    logger.info("Entity extraction complete: %d entities generated", total_generated)
    return summary


async def run_entity_extraction(
    config: dict,
    narrative_blocks: dict,
    timeline: dict | None = None,
    max_depth: int = 4,
    on_progress=None,
) -> dict:
    """Run entity extraction per era with cumulative context, falling back to iterative deepening.

    Modifies narrative_blocks in-place, adding entities_<type> keys.

    Args:
        config: World configuration.
        narrative_blocks: Current narrative blocks (modified in place).
        timeline: Simulation timeline dict (used to build structured context per era).
        max_depth: Maximum depth iterations for iterative fallback.
        on_progress: Optional async callback(message: str).

    Returns:
        Summary dict with total_generated, eras_processed, and counts per type.
    """
    eras = narrative_blocks.get("eras", [])
    if not eras or timeline is None:
        logger.info("No eras or no timeline — falling back to iterative entity extraction")
        return await _run_entity_extraction_iterative(config, narrative_blocks, max_depth=max_depth, on_progress=on_progress)

    # Sort eras chronologically
    sorted_eras = sorted(eras, key=lambda e: e.get("start_year", 0))
    total_generated = 0
    eras_processed = 0
    all_detected_names: list[str] = []

    # Collect characters and legends text for the first era
    chars_legends_parts = []
    for block_key in ["characters", "legends"]:
        items = narrative_blocks.get(block_key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and len(v) > 20:
                            chars_legends_parts.append(v)
    chars_legends_text = "\n\n".join(chars_legends_parts)

    for era_index, era in enumerate(sorted_eras):
        era_name = era.get("name", f"Ère {era_index + 1}")
        if on_progress:
            await on_progress(f"Extraction d'entités — {era_name} ({era_index + 1}/{len(sorted_eras)})")

        logger.info("Entity extraction for era '%s' (%d/%d)", era_name, era_index + 1, len(sorted_eras))

        era_text = _collect_era_narrative_text(narrative_blocks, era)
        structured_context = _build_era_structured_context(timeline, era)

        # For the first era, append characters + legends text and add volume hint
        if era_index == 0:
            if chars_legends_text:
                era_text = era_text + "\n\n" + chars_legends_text if era_text else chars_legends_text
            volume_hint = f"Ce monde comporte {len(config.get('factions', []))} factions — cherche au moins une entité par faction."
        else:
            volume_hint = ""

        new_entities = await detect_entities(
            narrative_blocks,
            config,
            era_text=era_text,
            structured_context=structured_context,
            previously_detected=list(all_detected_names),
            volume_hint=volume_hint,
        )

        if not new_entities:
            logger.info("No new entities found for era '%s'", era_name)
        else:
            logger.info("Found %d new entities for era '%s'", len(new_entities), era_name)

        # Generate sheets sequentially (Moonshot API does not support concurrent requests)
        failed_sheets = []
        for entity in new_entities:
            try:
                sheet = await generate_entity_sheet(entity, config, narrative_blocks)
                entity_type = entity.get("type", "artefact")
                block_key = f"entities_{entity_type}"
                if block_key not in narrative_blocks:
                    narrative_blocks[block_key] = []
                narrative_blocks[block_key].append(sheet)
                total_generated += 1

                entity_name = entity.get("name", "")
                if entity_name:
                    all_detected_names.append(entity_name)
            except Exception as e:
                entity_name = entity.get("name", "?")
                logger.error("Failed to generate sheet for '%s' in era '%s': %s", entity_name, era_name, e)
                failed_sheets.append(entity_name)
                # Still add the name to avoid re-detection
                if entity.get("name"):
                    all_detected_names.append(entity["name"])

        if failed_sheets:
            logger.warning("Era '%s': %d/%d entity sheets failed: %s", era_name, len(failed_sheets), len(new_entities), failed_sheets)

        # Generate cosmogonies for newly detected races
        races = narrative_blocks.get("entities_race", [])
        existing_cosmogonies = {
            c.get("race", "") for c in narrative_blocks.get("entities_cosmogonie", [])
            if isinstance(c, dict)
        }
        new_races = [r for r in races if isinstance(r, dict) and r.get("name", "") not in existing_cosmogonies]

        if new_races:
            if on_progress:
                await on_progress(f"Génération des cosmogonies — {era_name} ({len(new_races)} races)")
            for race in new_races:
                try:
                    cosmo = await generate_cosmogony(race, config, narrative_blocks)
                    if "entities_cosmogonie" not in narrative_blocks:
                        narrative_blocks["entities_cosmogonie"] = []
                    narrative_blocks["entities_cosmogonie"].append(cosmo)
                    total_generated += 1
                except Exception as e:
                    logger.error("Failed to generate cosmogony for '%s': %s", race.get("name", "?"), e)

        eras_processed += 1

    summary = {
        "total_generated": total_generated,
        "eras_processed": eras_processed,
        "counts": {},
    }
    for entity_type in ENTITY_TYPES + ["cosmogonie"]:
        key = f"entities_{entity_type}"
        count = len(narrative_blocks.get(key, []))
        if count > 0:
            summary["counts"][entity_type] = count

    logger.info(
        "Per-era entity extraction complete: %d entities generated across %d eras",
        total_generated,
        eras_processed,
    )
    return summary
