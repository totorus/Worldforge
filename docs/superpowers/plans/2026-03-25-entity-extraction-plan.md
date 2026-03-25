# Entity Extraction & Lore Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add entity detection, sheet generation (11 entity types), cosmogonies, auto-coherence correction, simulator validation, and extended Bookstack export with cross-references.

**Architecture:** New narrator modules handle entity extraction (Kimi detection → Mistral generation, 4 depth levels) and coherence auto-fix. Simulator gets a post-run validator. Exporter gets 9 new chapters with full cross-referencing.

**Tech Stack:** Python FastAPI, Kimi K2.5 (Moonshot API), Mistral Small Creative / Small 4 (OpenRouter), Bookstack REST API.

**Spec:** `docs/superpowers/specs/2026-03-25-entity-extraction-design.md`

---

### Task 1: Simulator Validator

**Files:**
- Create: `backend/app/simulator/validator.py`
- Modify: `backend/app/simulator/engine.py:17-49`
- Test: `backend/tests/test_validator.py`

- [ ] **Step 1: Write failing tests for simulator validator**

```python
# tests/test_validator.py
import pytest
from app.simulator.validator import validate_timeline


def test_dead_character_cannot_act():
    """A character retired in tick 2 must not appear in events after tick 2."""
    timeline = {
        "ticks": [
            {"year": 1, "character_events": [{"name_placeholder": "hero_1", "type": "spawn", "faction_id": "f1"}], "events": []},
            {"year": 2, "character_events": [{"name_placeholder": "hero_1", "type": "retire"}], "events": []},
            {"year": 3, "character_events": [], "events": [{"event_id": "battle_1", "involved_factions": ["f1"], "involved_characters": ["hero_1"]}]},
        ]
    }
    errors = validate_timeline(timeline, config={"factions": [{"id": "f1"}], "tech_tree": {"nodes": []}})
    assert any("hero_1" in e for e in errors)


def test_negative_population():
    """Population must never be negative."""
    timeline = {
        "ticks": [
            {"year": 1, "character_events": [], "events": [],
             "world_state": {"factions": [{"id": "f1", "population": -100, "regions": ["r1"], "attributes": {}, "unlocked_techs": []}]}}
        ]
    }
    errors = validate_timeline(timeline, config={"factions": [{"id": "f1"}], "tech_tree": {"nodes": []}})
    assert any("population" in e.lower() for e in errors)


def test_tech_prereqs_not_met():
    """A tech cannot be unlocked without its prerequisites."""
    config = {
        "factions": [{"id": "f1"}],
        "tech_tree": {"nodes": [
            {"id": "basic", "prerequisites": []},
            {"id": "advanced", "prerequisites": ["basic"]},
        ]}
    }
    timeline = {
        "ticks": [
            {"year": 1, "character_events": [], "events": [],
             "tech_unlocks": [{"faction_id": "f1", "tech_id": "advanced"}],
             "world_state": {"factions": [{"id": "f1", "population": 100, "regions": ["r1"], "attributes": {}, "unlocked_techs": ["advanced"]}]}}
        ]
    }
    errors = validate_timeline(timeline, config=config)
    assert any("advanced" in e for e in errors)


def test_valid_timeline_no_errors():
    """A valid timeline produces no errors."""
    config = {
        "factions": [{"id": "f1"}],
        "tech_tree": {"nodes": [{"id": "basic", "prerequisites": []}]}
    }
    timeline = {
        "ticks": [
            {"year": 1, "character_events": [{"name_placeholder": "hero_1", "type": "spawn", "faction_id": "f1"}],
             "events": [], "tech_unlocks": [{"faction_id": "f1", "tech_id": "basic"}],
             "world_state": {"factions": [{"id": "f1", "population": 100, "regions": ["r1"], "attributes": {}, "unlocked_techs": ["basic"]}]}}
        ]
    }
    errors = validate_timeline(timeline, config=config)
    assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_validator.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement validator**

```python
# app/simulator/validator.py
"""Post-simulation validator — checks timeline invariants."""

import logging

logger = logging.getLogger("worldforge.simulator.validator")


def validate_timeline(timeline: dict, config: dict) -> list[str]:
    """Validate timeline invariants. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Build tech prerequisite map
    tech_nodes = {t["id"]: t for t in config.get("tech_tree", {}).get("nodes", [])}

    # Track character lifecycle
    alive_characters: dict[str, int] = {}   # placeholder -> spawn year
    dead_characters: dict[str, int] = {}    # placeholder -> retire year

    # Track faction unlocked techs
    faction_techs: dict[str, set[str]] = {f["id"]: set() for f in config.get("factions", [])}

    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)

        # Character lifecycle
        for ce in tick.get("character_events", []):
            placeholder = ce.get("name_placeholder", "")
            if ce.get("type") == "spawn":
                alive_characters[placeholder] = year
            elif ce.get("type") == "retire":
                if placeholder in alive_characters:
                    dead_characters[placeholder] = year
                    del alive_characters[placeholder]

        # Check dead characters in events
        for evt in tick.get("events", []):
            for char in evt.get("involved_characters", []):
                if char in dead_characters:
                    errors.append(
                        f"Année {year}: personnage '{char}' mort en {dead_characters[char]} "
                        f"impliqué dans l'événement '{evt.get('event_id', '?')}'"
                    )

        # Tech prerequisite validation
        for tu in tick.get("tech_unlocks", []):
            fac_id = tu.get("faction_id", "")
            tech_id = tu.get("tech_id", "")
            tech_def = tech_nodes.get(tech_id)
            if tech_def:
                for prereq in tech_def.get("prerequisites", []):
                    if prereq not in faction_techs.get(fac_id, set()):
                        errors.append(
                            f"Année {year}: faction '{fac_id}' débloque '{tech_id}' "
                            f"sans prérequis '{prereq}'"
                        )
            faction_techs.setdefault(fac_id, set()).add(tech_id)

        # World state checks
        ws = tick.get("world_state", {})
        for fac in ws.get("factions", []):
            fac_id = fac.get("id", "?")
            pop = fac.get("population", 0)
            if pop < 0:
                errors.append(f"Année {year}: faction '{fac_id}' a une population négative ({pop})")

    if errors:
        logger.warning("Timeline validation: %d errors found", len(errors))
    else:
        logger.info("Timeline validation: OK")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_validator.py -v`
Expected: All PASS

- [ ] **Step 5: Integrate validator into engine.py**

In `engine.py`, after `run_simulation()` returns, call the validator. Add at the end of `run_simulation()` before the return:

```python
from app.simulator.validator import validate_timeline

# ... end of run_simulation, before return:
    errors = validate_timeline(timeline_result, config)
    if errors:
        timeline_result["validation_errors"] = errors

    return timeline_result
```

Where `timeline_result` is the dict being built. The actual variable name is the inline dict — refactor to:

```python
    result = {
        "world_id": world_id,
        "config_hash": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "seed": seed,
        "ticks": ticks,
    }

    validation_errors = validate_timeline(result, config)
    if validation_errors:
        result["validation_errors"] = validation_errors

    return result
```

- [ ] **Step 6: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/simulator/validator.py backend/tests/test_validator.py backend/app/simulator/engine.py
git commit -m "feat: add post-simulation timeline validator with invariant checks"
```

---

### Task 2: LLM Router — New Task Types

**Files:**
- Modify: `backend/app/services/llm_router.py:6-23`

- [ ] **Step 1: Add new task types to TASK_ROUTING**

Add these entries to the `TASK_ROUTING` dict:

```python
    # Entity extraction (Kimi K2.5)
    "entity_detection": "kimi",

    # Entity sheet generation (Mistral Creative)
    "entity_sheet": "mistral_creative",
    "cosmogony": "mistral_creative",
    "race_sheet": "mistral_creative",
    "fauna_sheet": "mistral_creative",
    "flora_sheet": "mistral_creative",
    "bestiary_sheet": "mistral_creative",
    "location_sheet": "mistral_creative",
    "resource_sheet": "mistral_creative",
    "organization_sheet": "mistral_creative",
    "artifact_sheet": "mistral_creative",

    # Coherence fix (Mistral Creative — rewrites narrative blocks)
    "coherence_fix": "mistral_creative",
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/llm_router.py
git commit -m "feat: add LLM routing for entity detection, sheet generation, and coherence fix"
```

---

### Task 3: Entity Extraction Module

**Files:**
- Create: `backend/app/narrator/entity_extraction.py`
- Test: `backend/tests/test_entity_extraction.py`

- [ ] **Step 1: Write entity type constants and detection prompt builder**

```python
# app/narrator/entity_extraction.py
"""Entity extraction — detects and generates sheets for invented entities in narrative blocks."""

import json
import logging
from app.narrator.json_utils import extract_json
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
```

- [ ] **Step 2: Write the detection function**

```python
async def detect_entities(
    narrative_blocks: dict,
    config: dict,
) -> list[dict]:
    """Detect invented entities mentioned in narrative blocks that lack their own sheet.

    Returns list of dicts: [{name, type, context}]
    """
    known = _build_known_entities(config, narrative_blocks)
    text = _collect_narrative_text(narrative_blocks)

    if not text:
        return []

    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Truncate text to fit context window
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texte tronqué...]"

    type_descriptions = "\n".join(
        f"- {t}: {info['description']}" for t, info in ENTITY_TEMPLATES.items()
    )

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un analyste de lore spécialisé dans les mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Ta tâche est d'identifier les entités inventées nommées dans le texte "
                "qui n'ont pas encore de fiche dédiée. "
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
                "- Un personnage historique doit avoir un impact fort sur l'histoire pour mériter une fiche\n\n"
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
        logger.info("Detected %d new entities (from %d candidates)", len(filtered), len(entities))
        return filtered
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse entity detection JSON: %s", e)
        return []
```

- [ ] **Step 3: Write the sheet generation function**

```python
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
                "Tu dois créer une fiche encyclopédique détaillée et immersive. "
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
                "Le contenu doit être cohérent avec le lore existant, "
                "riche en détails narratifs, et immersif."
            ),
        },
    ]

    logger.info("Generating sheet for entity '%s' (type=%s)", entity_name, entity_type)
    response = await llm_router.complete(
        task=llm_task, messages=messages, temperature=0.8, max_tokens=3072
    )

    try:
        sheet = extract_json(response)
        if not isinstance(sheet, dict):
            raise ValueError("Expected a JSON object")
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
```

- [ ] **Step 4: Write the main extraction loop (4 depth levels)**

```python
async def run_entity_extraction(
    config: dict,
    narrative_blocks: dict,
    max_depth: int = 4,
    on_progress=None,
) -> dict:
    """Run full entity extraction with iterative deepening.

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
        for entity in new_entities:
            sheet = await generate_entity_sheet(entity, config, narrative_blocks)

            # Store in narrative_blocks under entities_<type>
            entity_type = entity.get("type", "artefact")
            block_key = f"entities_{entity_type}"
            if block_key not in narrative_blocks:
                narrative_blocks[block_key] = []
            narrative_blocks[block_key].append(sheet)
            total_generated += 1

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
                cosmo = await generate_cosmogony(race, config, narrative_blocks)
                if "entities_cosmogonie" not in narrative_blocks:
                    narrative_blocks["entities_cosmogonie"] = []
                narrative_blocks["entities_cosmogonie"].append(cosmo)
                total_generated += 1

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
```

- [ ] **Step 5: Write the cosmogony generator**

```python
async def generate_cosmogony(
    race: dict,
    config: dict,
    narrative_blocks: dict,
) -> dict:
    """Generate a cosmogony for a detected race.

    Args:
        race: Race sheet dict.
        config: World configuration.
        narrative_blocks: Current narrative blocks.

    Returns:
        Cosmogony dict.
    """
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
```

- [ ] **Step 6: Write tests**

```python
# tests/test_entity_extraction.py
import pytest
from app.narrator.entity_extraction import (
    _build_known_entities,
    _collect_narrative_text,
    ENTITY_TYPES,
    ENTITY_TEMPLATES,
)


def test_build_known_entities_includes_factions():
    config = {"factions": [{"id": "f1", "name": "Elfes"}], "geography": {"regions": []}, "tech_tree": {"nodes": []}}
    blocks = {"characters": []}
    known = _build_known_entities(config, blocks)
    assert "Elfes" in known


def test_build_known_entities_includes_regions():
    config = {"factions": [], "geography": {"regions": [{"id": "r1", "name": "Velmorath"}]}, "tech_tree": {"nodes": []}}
    blocks = {"characters": []}
    known = _build_known_entities(config, blocks)
    assert "Velmorath" in known


def test_build_known_entities_includes_characters():
    config = {"factions": [], "geography": {"regions": []}, "tech_tree": {"nodes": []}}
    blocks = {"characters": [{"name": "Lyria Veyne"}]}
    known = _build_known_entities(config, blocks)
    assert "Lyria Veyne" in known


def test_collect_narrative_text_concatenates():
    blocks = {
        "factions": [{"name": "Elfes", "description": "Les Elfes sont un peuple ancien et mystérieux."}],
        "regions": [{"name": "Velmorath", "landscape": "Un paysage désolé de cendres et de ruines."}],
    }
    text = _collect_narrative_text(blocks)
    assert "peuple ancien" in text
    assert "cendres" in text


def test_all_entity_types_have_templates():
    for t in ENTITY_TYPES:
        assert t in ENTITY_TEMPLATES, f"Missing template for {t}"
```

- [ ] **Step 7: Run tests**

Run: `cd backend && python -m pytest tests/test_entity_extraction.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/narrator/entity_extraction.py backend/tests/test_entity_extraction.py
git commit -m "feat: add entity extraction module with detection, sheet generation, and cosmogonies"
```

---

### Task 4: Coherence Auto-Fix Module

**Files:**
- Create: `backend/app/narrator/coherence_fix.py`
- Modify: `backend/app/narrator/coherence.py`

- [ ] **Step 1: Create coherence_fix module**

```python
# app/narrator/coherence_fix.py
"""Coherence auto-fix — automatically corrects narrative inconsistencies."""

import json
import logging

from app.narrator.json_utils import extract_json
from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.coherence_fix")

# Map issue keywords to narrative block keys
_BLOCK_KEYWORDS = {
    "faction": "factions",
    "région": "regions",
    "personnage": "characters",
    "événement": "events",
    "légende": "legends",
    "ère": "eras",
}


def _identify_faulty_blocks(issues: list[str]) -> set[str]:
    """Identify which narrative block keys are implicated by coherence issues."""
    faulty = set()
    for issue in issues:
        issue_lower = issue.lower()
        for keyword, block_key in _BLOCK_KEYWORDS.items():
            if keyword in issue_lower:
                faulty.add(block_key)
    # If we can't identify specific blocks, target the most likely culprits
    if not faulty:
        faulty = {"factions", "regions", "characters"}
    return faulty


async def fix_coherence_issues(
    narrative_blocks: dict,
    config: dict,
    issues: list[str],
) -> dict:
    """Re-narrate faulty blocks with coherence issues as constraints.

    Args:
        narrative_blocks: Full narrative blocks dict.
        config: World config.
        issues: List of coherence issue strings from the check.

    Returns:
        Updated narrative_blocks dict with corrected blocks.
    """
    faulty_keys = _identify_faulty_blocks(issues)
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    logger.info("Fixing coherence issues in blocks: %s", faulty_keys)

    issues_text = "\n".join(f"- {issue}" for issue in issues)

    for block_key in faulty_keys:
        block_data = narrative_blocks.get(block_key)
        if not block_data:
            continue

        if not isinstance(block_data, list):
            continue

        # For each item in the block, ask LLM to fix it considering the issues
        corrected_items = []
        for item in block_data:
            if not isinstance(item, dict):
                corrected_items.append(item)
                continue

            item_name = item.get("name", item.get("title", "?"))
            item_json = json.dumps(item, ensure_ascii=False, indent=2)

            # Truncate if too long
            if len(item_json) > 3000:
                item_json = item_json[:3000] + "\n..."

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Tu es un relecteur et correcteur spécialisé dans la cohérence narrative. "
                        "Tu écris toujours en français. "
                        f"Le monde « {world_name} » est de genre « {genre} ». "
                        "Tu dois corriger les incohérences identifiées dans la fiche suivante "
                        "tout en préservant le style et le contenu qui ne pose pas de problème. "
                        "Réponds uniquement avec un JSON valide corrigé (sans markdown, sans commentaire)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Voici une fiche narrative pour « {item_name} » (type: {block_key}) :\n\n"
                        f"{item_json}\n\n"
                        f"Incohérences détectées dans le lore global :\n{issues_text}\n\n"
                        "Corrige UNIQUEMENT les incohérences qui concernent cette fiche. "
                        "Préserve tout le reste (style, détails, structure). "
                        "Si aucune incohérence ne concerne cette fiche, renvoie-la telle quelle. "
                        "Réponds avec le JSON corrigé de la fiche."
                    ),
                },
            ]

            response = await llm_router.complete(
                task="coherence_fix", messages=messages, temperature=0.3, max_tokens=3072
            )

            try:
                corrected = extract_json(response)
                if isinstance(corrected, dict):
                    # Preserve ID and name from original
                    corrected["id"] = item.get("id", item.get("name", ""))
                    corrected["name"] = item.get("name", corrected.get("name", ""))
                    corrected_items.append(corrected)
                else:
                    corrected_items.append(item)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse corrected item for '%s', keeping original", item_name)
                corrected_items.append(item)

        narrative_blocks[block_key] = corrected_items

    return narrative_blocks
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/narrator/coherence_fix.py
git commit -m "feat: add coherence auto-fix module for narrative blocks"
```

---

### Task 5: Pipeline Integration

**Files:**
- Modify: `backend/app/narrator/pipeline.py`

- [ ] **Step 1: Update ALL_STEPS and imports**

Add imports for new modules and update the step list:

```python
from app.narrator.entity_extraction import run_entity_extraction
from app.narrator.coherence_fix import fix_coherence_issues
```

Update `ALL_STEPS`:

```python
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
```

- [ ] **Step 2: Add entity extraction runner**

```python
async def _run_entity_extraction(config: dict, narrative_blocks: dict) -> dict:
    """Run entity extraction with iterative deepening."""
    return await run_entity_extraction(config, narrative_blocks, max_depth=4)
```

- [ ] **Step 3: Add coherence auto-fix loop to run_narration**

Replace the coherence check section in `run_narration()` with a loop:

```python
    # Step 8: Entity extraction
    logger.info("Step 8/9: Entity extraction")
    narrative_blocks["entity_summary"] = await _run_entity_extraction(config, narrative_blocks)

    # Step 9: Coherence check with auto-fix loop
    logger.info("Step 9/9: Coherence check")
    coherence_threshold = 0.75
    max_coherence_iterations = 3

    for iteration in range(1, max_coherence_iterations + 1):
        logger.info("Coherence check iteration %d/%d", iteration, max_coherence_iterations)
        report = await _run_coherence_check(config, narrative_blocks)
        narrative_blocks["coherence_report"] = report

        score = report.get("score", 0.5)
        issues = report.get("issues", [])

        if score >= coherence_threshold or not issues:
            logger.info("Coherence score %.2f >= %.2f, accepted", score, coherence_threshold)
            break

        logger.info("Coherence score %.2f < %.2f, fixing issues (%d found)", score, coherence_threshold, len(issues))

        if iteration < max_coherence_iterations:
            narrative_blocks = await fix_coherence_issues(narrative_blocks, config, issues)
            # Fix updates blocks in-place, re-check on next iteration
        else:
            logger.warning("Coherence still below threshold after %d iterations, proceeding anyway", max_coherence_iterations)
            report["warning"] = f"Score de cohérence ({score:.2f}) inférieur au seuil ({coherence_threshold}) après {max_coherence_iterations} corrections."
            narrative_blocks["coherence_report"] = report
```

- [ ] **Step 4: Update run_partial_narration with new steps**

Add `entity_extraction` to `step_runners` and `block_keys`:

```python
        "entity_extraction": lambda: _run_entity_extraction(config, narrative_blocks),
```

```python
        "entity_extraction": "entity_summary",
```

- [ ] **Step 5: Update run_narration step numbering**

Update all log messages from "Step X/8" to "Step X/9".

- [ ] **Step 6: Commit**

```bash
git add backend/app/narrator/pipeline.py
git commit -m "feat: integrate entity extraction and coherence auto-fix into narration pipeline"
```

---

### Task 6: Narrator Router Updates

**Files:**
- Modify: `backend/app/routers/narrate.py:28-37,81-141`

- [ ] **Step 1: Update step labels**

```python
_STEP_LABELS = {
    0: "Découpage en ères",
    1: "Nommage",
    2: "Fiches de factions",
    3: "Fiches de régions",
    4: "Narration des événements",
    5: "Biographies des personnages",
    6: "Légendes",
    7: "Extraction d'entités",
    8: "Vérification de cohérence",
}
```

- [ ] **Step 2: Update background runner step count**

In `_run_narration_background`, update `total_steps = 9` and add the entity extraction step runner:

```python
        step_runners = [
            ("eras", lambda: _run_era_splitting(config, timeline)),
            ("names", lambda: _run_naming(config, timeline)),
            ("factions", lambda: _run_faction_sheets(config, timeline)),
            ("regions", lambda: _run_region_sheets(config, timeline)),
            ("events", lambda: _run_event_narratives(config, timeline, narrative_blocks)),
            ("characters", lambda: _run_character_bios(config, timeline, narrative_blocks)),
            ("legends", lambda: _run_legends(config, narrative_blocks)),
            ("entity_summary", lambda: _run_entity_extraction(config, narrative_blocks)),
            ("coherence_report", lambda: _run_coherence_check_with_fix(config, narrative_blocks)),
        ]
```

This requires importing `_run_entity_extraction` from pipeline and creating a wrapper `_run_coherence_check_with_fix` that encapsulates the auto-fix loop. Alternatively, refactor the loop into the pipeline module and import it.

- [ ] **Step 3: Import new pipeline functions**

```python
from app.narrator.pipeline import (
    _run_era_splitting, _run_naming, _run_faction_sheets,
    _run_region_sheets, _run_event_narratives, _run_character_bios,
    _run_legends, _run_coherence_check, _run_entity_extraction,
    run_coherence_with_fix,
)
```

Create `run_coherence_with_fix` in pipeline.py:

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/narrate.py backend/app/narrator/pipeline.py
git commit -m "feat: update narration router for entity extraction step and coherence auto-fix"
```

---

### Task 7: Entity Formatters

**Files:**
- Modify: `backend/app/exporter/formatters.py`

- [ ] **Step 1: Add format_race_page**

```python
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
```

- [ ] **Step 2: Add format_cosmogony_page**

```python
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
```

- [ ] **Step 3: Add format_fauna_page, format_flora_page, format_bestiary_page**

```python
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
```

- [ ] **Step 4: Add format_notable_location_page, format_resource_page, format_organization_page, format_artifact_page**

```python
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
```

- [ ] **Step 5: Update format_character_page with description_physique and statut_actuel**

Add to `format_character_page` after the meta section:

```python
    # Physical description
    description_physique = character.get("description_physique", "")
    if description_physique:
        parts.append(f"<h3>Description physique</h3>{_markdown_to_html(description_physique)}")

    # Race
    race = character.get("race", "")
    if race:
        meta_parts.append(f"<strong>Race :</strong> {_e(race)}")

    # Current status
    statut = character.get("statut_actuel", "")
    if statut:
        meta_parts.append(f"<strong>Statut :</strong> {_e(statut)}")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/exporter/formatters.py
git commit -m "feat: add formatters for all new entity types (race, cosmogony, fauna, flora, bestiary, locations, resources, organizations, artifacts)"
```

---

### Task 8: Exporter Pipeline — New Chapters & Extended Cross-References

**Files:**
- Modify: `backend/app/exporter/pipeline.py`

- [ ] **Step 1: Import new formatters**

```python
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
```

- [ ] **Step 2: Add new chapter definitions**

Update `chapter_defs` list to add 9 new chapters:

```python
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
```

- [ ] **Step 3: Add page creation for each new entity type**

After the existing Légendes section and before Annexes, add:

```python
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
```

- [ ] **Step 4: Cross-references already work** — the existing pass 2 (`_inject_cross_references`) builds `xref_map` from ALL `pages_created`, so new entity pages are automatically included. No changes needed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/exporter/pipeline.py
git commit -m "feat: add 9 new Bookstack chapters for entities with full cross-referencing"
```

---

### Task 9: Integration Test

**Files:**
- Create: `backend/tests/test_entity_integration.py`

- [ ] **Step 1: Write integration test for entity detection pipeline**

```python
# tests/test_entity_integration.py
"""Integration test for entity extraction in the narration pipeline."""
import pytest
from app.narrator.entity_extraction import (
    _build_known_entities,
    _collect_narrative_text,
    ENTITY_TYPES,
)


def test_known_entities_deduplication():
    """Known entities should not contain duplicates."""
    config = {
        "factions": [{"id": "f1", "name": "Elfes"}, {"id": "f2", "name": "Nains"}],
        "geography": {"regions": [{"id": "r1", "name": "Velmorath"}]},
        "tech_tree": {"nodes": []},
    }
    blocks = {
        "characters": [{"name": "Lyria"}, {"name": "Thalassar"}],
        "entities_race": [{"name": "Drakonides"}],
    }
    known = _build_known_entities(config, blocks)
    assert len(known) == len(set(known)), "Known entities should not have duplicates"


def test_entity_blocks_naming_convention():
    """All entity types should follow entities_<type> naming."""
    for t in ENTITY_TYPES:
        assert not t.startswith("entities_"), f"ENTITY_TYPES should not include prefix: {t}"
        block_key = f"entities_{t}"
        assert isinstance(block_key, str)


def test_narrative_text_collection_skips_short():
    """Short strings (< 20 chars) should be skipped."""
    blocks = {
        "factions": [{"name": "Elfes", "id": "f1", "description": "A very long description of the elves and their culture."}],
    }
    text = _collect_narrative_text(blocks)
    assert "Elfes" not in text  # "Elfes" is < 20 chars
    assert "very long description" in text
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_entity_integration.py
git commit -m "test: add integration tests for entity extraction"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Verify imports resolve correctly**

Run: `cd backend && python -c "from app.narrator.pipeline import ALL_STEPS, run_narration, run_coherence_with_fix; print('OK', ALL_STEPS)"`

- [ ] **Step 2: Verify entity extraction module imports**

Run: `cd backend && python -c "from app.narrator.entity_extraction import run_entity_extraction, detect_entities, generate_cosmogony; print('OK')"`

- [ ] **Step 3: Verify formatters import**

Run: `cd backend && python -c "from app.exporter.formatters import format_race_page, format_cosmogony_page, format_fauna_page, format_flora_page, format_bestiary_page, format_notable_location_page, format_resource_page, format_organization_page, format_artifact_page; print('OK')"`

- [ ] **Step 4: Verify exporter imports**

Run: `cd backend && python -c "from app.exporter.pipeline import export_to_bookstack; print('OK')"`

- [ ] **Step 5: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete entity extraction, lore enrichment, and auto-coherence — closes entity-extraction feature"
```
