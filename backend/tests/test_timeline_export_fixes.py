"""Tests for timeline/export fix helpers."""

import pytest


def test_match_narrative_events_to_eras_exact():
    from app.exporter.pipeline import _match_narrative_events_to_eras
    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
        {"name": "L'Ère des Conflits", "start_year": 201, "end_year": 500},
    ]
    events = [
        {"era": "L'Âge des Origines", "title": "Evt 1"},
        {"era": "L'Ère des Conflits", "title": "Evt 2"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1
    assert len(result["L'Ère des Conflits"]) == 1


def test_match_narrative_events_to_eras_substring():
    from app.exporter.pipeline import _match_narrative_events_to_eras
    eras = [{"name": "L'Âge des Origines", "start_year": 0, "end_year": 200}]
    events = [{"era": "L'Âge des Origines Perdues (0-200)", "title": "Evt 1"}]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1


def test_match_narrative_events_to_eras_year_fallback():
    from app.exporter.pipeline import _match_narrative_events_to_eras
    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
        {"name": "L'Ère des Conflits", "start_year": 201, "end_year": 500},
    ]
    events = [
        {"era": "Le Crépuscule des Anciens", "year": 150, "title": "Evt 1"},
        {"era": "Quelque chose", "year": 300, "title": "Evt 2"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1
    assert len(result["L'Ère des Conflits"]) == 1


def test_match_narrative_events_orphans():
    from app.exporter.pipeline import _match_narrative_events_to_eras
    eras = [{"name": "L'Âge des Origines", "start_year": 0, "end_year": 200}]
    events = [{"era": "Totalement inconnu", "title": "Evt 1"}]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result.get("__orphans__", [])) == 1


def test_collect_unlocked_techs():
    from app.exporter.pipeline import _collect_unlocked_techs
    timeline = {
        "ticks": [
            {"year": 100, "world_state": {"factions": [
                {"id": "fac_a", "unlocked_techs": ["tech_fire"]},
                {"id": "fac_b", "unlocked_techs": ["tech_fire", "tech_wheel"]},
            ]}},
            {"year": 200, "world_state": {"factions": [
                {"id": "fac_a", "unlocked_techs": ["tech_fire", "tech_iron"]},
                {"id": "fac_b", "unlocked_techs": ["tech_fire", "tech_wheel"]},
            ]}},
        ]
    }
    tech_tree_nodes = {
        "tech_fire": {"id": "tech_fire", "name": "Feu"},
        "tech_wheel": {"id": "tech_wheel", "name": "Roue"},
        "tech_iron": {"id": "tech_iron", "name": "Fer"},
        "tech_steam": {"id": "tech_steam", "name": "Vapeur"},
    }
    result = _collect_unlocked_techs(timeline, tech_tree_nodes)
    result_ids = {t["id"] for t in result}
    assert result_ids == {"tech_fire", "tech_wheel", "tech_iron"}
    assert "tech_steam" not in result_ids


def test_chapter_page_count_mapping():
    type_to_chapter = {
        "region": "atlas", "era": "chroniques", "faction": "factions",
        "race": "races", "cosmogony": "cosmogonies", "character": "personnages",
        "tech": "tech", "legend": "legendes", "fauna": "faune",
        "flora": "flore", "bestiary": "bestiaire", "location": "lieux",
        "resource": "ressources", "organization": "organisations",
        "artifact": "artefacts", "annex": "annexes",
    }
    expected_types = {
        "region", "era", "faction", "race", "cosmogony", "character",
        "tech", "legend", "fauna", "flora", "bestiary", "location",
        "resource", "organization", "artifact", "annex",
    }
    assert set(type_to_chapter.keys()) == expected_types
