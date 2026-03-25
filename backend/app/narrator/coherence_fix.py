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
