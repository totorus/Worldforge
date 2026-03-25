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
