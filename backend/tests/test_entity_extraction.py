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
