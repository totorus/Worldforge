# app/narrator/coherence_fix.py
"""Coherence auto-fix — automatically corrects narrative inconsistencies."""

import json
import logging

from app.narrator.json_utils import extract_json, unwrap_llm_json
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


def _issue_to_str(issue) -> str:
    """Convert an issue to string (LLM may return dicts or strings)."""
    if isinstance(issue, str):
        return issue
    if isinstance(issue, dict):
        return issue.get("description", issue.get("issue", issue.get("detail", str(issue))))
    return str(issue)


def _identify_faulty_blocks(issues: list) -> set[str]:
    """Identify which narrative block keys are implicated by coherence issues."""
    faulty = set()
    for issue in issues:
        issue_lower = _issue_to_str(issue).lower()
        for keyword, block_key in _BLOCK_KEYWORDS.items():
            if keyword in issue_lower:
                faulty.add(block_key)
    # If we can't identify specific blocks, target the most likely culprits
    if not faulty:
        faulty = {"characters"}
    return faulty


def _find_affected_items(block_data: list, issues: list) -> list[int]:
    """Find indices of items in a block that are mentioned in issues."""
    affected = []
    issues_text_lower = " ".join(_issue_to_str(i) for i in issues).lower()
    for i, item in enumerate(block_data):
        if not isinstance(item, dict):
            continue
        item_name = item.get("name", item.get("title", "")).lower()
        if not item_name:
            continue
        if item_name in issues_text_lower:
            affected.append(i)
    return affected


async def fix_coherence_issues(
    narrative_blocks: dict,
    config: dict,
    issues: list[str],
) -> dict:
    """Fix coherence issues with coordinated corrections across related items.

    Instead of fixing each item individually, groups affected items and fixes
    them in a single LLM call so corrections are consistent with each other.
    """
    faulty_keys = _identify_faulty_blocks(issues)
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    logger.info("Fixing coherence issues in blocks: %s", faulty_keys)

    issues_text = "\n".join(f"- {_issue_to_str(issue)}" for issue in issues)

    for block_key in faulty_keys:
        block_data = narrative_blocks.get(block_key)
        if not block_data or not isinstance(block_data, list):
            continue

        # Find which items are actually mentioned in the issues
        affected_indices = _find_affected_items(block_data, issues)

        # If no specific items found, skip this block rather than fixing everything
        if not affected_indices:
            logger.info("No specific items found for block '%s', skipping", block_key)
            continue

        # Build a coordinated fix request with all affected items
        affected_items = []
        for idx in affected_indices:
            item = block_data[idx]
            item_json = json.dumps(item, ensure_ascii=False, indent=2)
            if len(item_json) > 2000:
                item_json = item_json[:2000] + "\n..."
            affected_items.append({
                "index": idx,
                "name": item.get("name", item.get("title", "?")),
                "json": item_json,
            })

        # Cap to avoid too-large prompts
        if len(affected_items) > 6:
            affected_items = affected_items[:6]

        items_block = "\n\n".join(
            f"=== Fiche {ai['index']+1}: « {ai['name']} » ===\n{ai['json']}"
            for ai in affected_items
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un relecteur spécialisé dans la cohérence narrative. "
                    "Tu écris toujours en français. "
                    f"Le monde « {world_name} » est de genre « {genre} ». "
                    "Tu reçois PLUSIEURS fiches qui sont liées aux mêmes incohérences. "
                    "Tu dois les corriger DE MANIÈRE COORDONNÉE — les corrections doivent "
                    "être cohérentes entre elles. "
                    "Préserve le style et le contenu qui ne pose pas de problème. "
                    "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Voici {len(affected_items)} fiches narratives (type: {block_key}) "
                    f"impliquées dans des incohérences :\n\n"
                    f"{items_block}\n\n"
                    f"Incohérences détectées :\n{issues_text}\n\n"
                    "Corrige UNIQUEMENT les incohérences qui concernent ces fiches. "
                    "Les corrections doivent être COORDONNÉES entre les fiches. "
                    "Si une fiche n'est pas concernée, renvoie-la telle quelle.\n\n"
                    "Réponds avec une liste JSON contenant les fiches corrigées, "
                    "dans le même ordre."
                ),
            },
        ]

        response = await llm_router.complete(
            task="coherence_fix", messages=messages, temperature=0.3, max_tokens=4096
        )

        try:
            corrected_list = extract_json(response)
            corrected_list = unwrap_llm_json(corrected_list, expect_list=True)

            if not isinstance(corrected_list, list):
                logger.warning("Coherence fix for '%s' returned non-list, skipping", block_key)
                continue

            # Apply corrections back to the original block
            for ci, ai in enumerate(affected_items):
                if ci >= len(corrected_list):
                    break
                corrected = corrected_list[ci]
                if not isinstance(corrected, dict):
                    continue
                idx = ai["index"]
                original = block_data[idx]
                # Preserve ID and name from original
                if isinstance(original, dict):
                    corrected["id"] = original.get("id", original.get("name", ""))
                    corrected["name"] = original.get("name", corrected.get("name", ""))
                block_data[idx] = corrected

            logger.info("Fixed %d items in block '%s'", len(affected_items), block_key)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse coordinated fix for '%s': %s", block_key, e)

    return narrative_blocks
