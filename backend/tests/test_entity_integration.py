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
