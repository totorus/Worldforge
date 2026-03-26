from app.narrator.json_utils import extract_json, unwrap_llm_json
"""Coherence check — validates narrative content for internal consistency."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.coherence")


def _to_str(value, max_len: int = 150) -> str:
    """Safely convert a value to a truncated string."""
    if isinstance(value, str):
        return value[:max_len]
    if isinstance(value, list):
        return str(value)[:max_len]
    if value is None:
        return ""
    return str(value)[:max_len]


async def check_coherence(narrative_blocks: dict, config: dict, *, registry=None) -> dict:
    """Send all narrative content to LLM for coherence validation.

    Args:
        narrative_blocks: Complete narrative_blocks dict.
        config: World configuration.

    Returns:
        Dict with keys: score (float 0-1), issues (list), suggestions (list)
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Build a condensed summary of all narrative content
    summary_parts = []

    # Helper to safely get from dict-or-string items
    def _safe_get(item, key, default="?"):
        if isinstance(item, dict):
            return item.get(key, default)
        return str(item)[:150] if isinstance(item, str) else default

    # Eras
    eras = narrative_blocks.get("eras", [])
    if eras:
        summary_parts.append("ÈRES :")
        for era in eras:
            if not isinstance(era, dict):
                continue
            summary_parts.append(f"  - {era.get('name', '?')} ({era.get('start_year', '?')}-{era.get('end_year', '?')}): {_to_str(era.get('description', ''))}")

    # Factions
    factions = narrative_blocks.get("factions", [])
    if factions:
        summary_parts.append("\nFACTIONS :")
        for fac in factions:
            if not isinstance(fac, dict):
                continue
            summary_parts.append(f"  - {fac.get('name', '?')}: {_to_str(fac.get('description', ''))}")

    # Regions
    regions = narrative_blocks.get("regions", [])
    if regions:
        summary_parts.append("\nRÉGIONS :")
        for reg in regions:
            if not isinstance(reg, dict):
                continue
            summary_parts.append(f"  - {reg.get('name', '?')}: {_to_str(reg.get('description', ''))}")

    # Key events
    events = narrative_blocks.get("events", [])
    if events:
        summary_parts.append("\nÉVÉNEMENTS CLÉS :")
        for evt in events[:20]:
            if not isinstance(evt, dict):
                continue
            summary_parts.append(f"  - An {evt.get('year', '?')} — {evt.get('title', '?')}: {_to_str(evt.get('narrative', ''), 100)}")

    # Characters
    characters = narrative_blocks.get("characters", [])
    if characters:
        summary_parts.append("\nPERSONNAGES :")
        for char in characters[:10]:
            if not isinstance(char, dict):
                continue
            summary_parts.append(f"  - {char.get('name', '?')} ({char.get('faction', '?')}, {char.get('role', '?')}): {_to_str(char.get('biography', ''), 100)}")

    # Legends
    legends = narrative_blocks.get("legends", [])
    if legends:
        summary_parts.append("\nLÉGENDES :")
        for leg in legends:
            if not isinstance(leg, dict):
                summary_parts.append(f"  - {_to_str(leg, 100)}")
                continue
            summary_parts.append(f"  - {leg.get('title', '?')}: {_to_str(leg.get('narrative', ''), 100)}")

    content_summary = "\n".join(summary_parts)

    # Build registry context or fallback to config
    if registry:
        known_context = registry.compact_summary(max_chars=600)
    else:
        faction_names = [f["name"] for f in config.get("factions", [])]
        region_names = [r["name"] for r in config.get("geography", {}).get("regions", [])]
        known_context = f"Factions : {', '.join(faction_names)}\nRégions : {', '.join(region_names)}"

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un relecteur et éditeur spécialisé dans la cohérence INTERNE de mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "IMPORTANT : tu juges la COHÉRENCE INTERNE du lore, PAS sa fidélité à une config initiale. "
                "Les nouvelles factions, organisations ou entités introduites pendant la narration sont LÉGITIMES "
                "si elles sont contextualisées (un schisme, une fondation, une découverte). "
                "Ne sanctionne PAS l'apparition de nouveaux noms — sanctionne uniquement :\n"
                "- Les contradictions factuelles (un personnage mort qui réapparaît vivant)\n"
                "- Les anachronismes (événement daté avant la fondation d'une faction qui y participe)\n"
                "- Les circularités logiques (A fondé par B, mais B membre fondateur de A)\n"
                "- Les références orphelines (nom mentionné une seule fois sans contexte)\n"
                "- Les incohérences chronologiques (durées impossibles, chevauchements d'ères)\n"
                "CALIBRATION DU SCORE :\n"
                "- 0.9-1.0 : aucune contradiction, chronologie parfaite\n"
                "- 0.75-0.9 : quelques ambiguïtés mineures mais pas de contradiction directe\n"
                "- 0.5-0.75 : contradictions factuelles ou anachronismes avérés\n"
                "- <0.5 : incohérences majeures rendant le lore inutilisable\n"
                "Les ambiguïtés narratives (noms similaires, sous-périodes non explicites) "
                "sont des imperfections MINEURES, pas des contradictions. "
                "Ne pénalise pas lourdement les détails stylistiques ou les nuances d'interprétation.\n"
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyse la cohérence interne du monde « {world_name} ».\n\n"
                f"Entités connues du monde :\n{known_context}\n\n"
                f"Contenu narratif :\n{content_summary}\n\n"
                "Évalue la cohérence interne et identifie les problèmes.\n"
                "Réponds avec un JSON contenant :\n"
                "- score : note de cohérence de 0.0 (contradictions majeures) à 1.0 (parfaitement cohérent). "
                "Un score de 0.7+ signifie que le lore est utilisable malgré des imperfections mineures.\n"
                "- issues : liste d'incohérences RÉELLES détectées (contradictions, anachronismes, circularités). "
                "Ne liste PAS les nouvelles entités comme des problèmes.\n"
                "- suggestions : liste de suggestions d'amélioration concrètes\n"
            ),
        },
    ]

    logger.info("Running coherence check for world '%s'", world_name)
    response = await llm_router.complete(
        task="coherence_check", messages=messages, temperature=0.3, max_tokens=3072
    )

    try:
        result = extract_json(response)
        result = unwrap_llm_json(result, expect_dict=True)
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        # Normalize score
        score = result.get("score", 0.5)
        if isinstance(score, (int, float)):
            score = max(0.0, min(1.0, float(score)))
        else:
            score = 0.5
        # Normalize issues/suggestions to strings (LLM may return dicts)
        raw_issues = result.get("issues", [])
        issues = [
            i if isinstance(i, str) else i.get("description", i.get("issue", str(i)))
            for i in raw_issues if i
        ] if isinstance(raw_issues, list) else []
        raw_suggestions = result.get("suggestions", [])
        suggestions = [
            s if isinstance(s, str) else s.get("description", s.get("suggestion", str(s)))
            for s in raw_suggestions if s
        ] if isinstance(raw_suggestions, list) else []
        return {
            "score": score,
            "issues": issues,
            "suggestions": suggestions,
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse coherence check JSON: %s", e)
        return {
            "score": 0.5,
            "issues": ["Impossible d'effectuer la vérification de cohérence automatique."],
            "suggestions": ["Relire manuellement le contenu narratif."],
        }
