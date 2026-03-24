"""Tests for world configuration validator."""

import copy
import json
from pathlib import Path

import pytest

from app.services.world_validator import validate_world_config

EXAMPLE_PATH = Path(__file__).resolve().parent.parent.parent / "world_config_example.json"


@pytest.fixture
def valid_config():
    return json.loads(EXAMPLE_PATH.read_text())


# --- Happy path ---

def test_example_config_is_valid(valid_config):
    errors = validate_world_config(valid_config)
    assert errors == [], [e.dict() for e in errors]


# --- Schema violations ---

def test_missing_meta(valid_config):
    del valid_config["meta"]
    errors = validate_world_config(valid_config)
    assert any("meta" in e.message for e in errors)


def test_invalid_chaos_level(valid_config):
    valid_config["meta"]["chaos_level"] = 1.5
    errors = validate_world_config(valid_config)
    assert len(errors) > 0


def test_too_few_regions(valid_config):
    valid_config["geography"]["regions"] = [valid_config["geography"]["regions"][0]]
    errors = validate_world_config(valid_config)
    assert len(errors) > 0


def test_too_few_factions(valid_config):
    valid_config["factions"] = [valid_config["factions"][0]]
    errors = validate_world_config(valid_config)
    assert len(errors) > 0


def test_invalid_tick_duration(valid_config):
    valid_config["meta"]["tick_duration_years"] = 3
    errors = validate_world_config(valid_config)
    assert len(errors) > 0


# --- Referential integrity ---

def test_region_references_nonexistent_resource(valid_config):
    valid_config["geography"]["regions"][0]["resources"].append("res_nonexistent")
    errors = validate_world_config(valid_config)
    assert any("res_nonexistent" in e.message for e in errors)


def test_tech_references_nonexistent_prerequisite(valid_config):
    valid_config["tech_tree"]["nodes"][0]["prerequisites"].append("tech_nonexistent")
    errors = validate_world_config(valid_config)
    assert any("tech_nonexistent" in e.message for e in errors)


def test_initial_state_references_nonexistent_faction(valid_config):
    valid_config["initial_state"]["faction_states"][0]["faction_id"] = "fac_ghost"
    errors = validate_world_config(valid_config)
    assert any("fac_ghost" in e.message for e in errors)


def test_initial_state_references_nonexistent_region(valid_config):
    valid_config["initial_state"]["faction_states"][0]["starting_regions"] = ["reg_void"]
    errors = validate_world_config(valid_config)
    assert any("reg_void" in e.message for e in errors)


def test_initial_state_references_nonexistent_tech(valid_config):
    valid_config["initial_state"]["faction_states"][0]["unlocked_techs"].append("tech_ghost")
    errors = validate_world_config(valid_config)
    assert any("tech_ghost" in e.message for e in errors)


# --- Bidirectional connections ---

def test_unidirectional_connection_detected(valid_config):
    # Remove the reverse connection from reg_forest -> reg_plains
    forest = next(r for r in valid_config["geography"]["regions"] if r["id"] == "reg_forest")
    forest["connections"] = [c for c in forest["connections"] if c["target"] != "reg_plains"]
    errors = validate_world_config(valid_config)
    assert any("bidirectionnelle" in e.message for e in errors)


# --- Tech cycles ---

def test_tech_cycle_detected(valid_config):
    # Create a cycle: agriculture requires navigation, navigation requires agriculture
    nodes = valid_config["tech_tree"]["nodes"]
    agri = next(n for n in nodes if n["id"] == "tech_agriculture")
    agri["prerequisites"] = ["tech_navigation"]
    errors = validate_world_config(valid_config)
    assert any("Cycle" in e.message or "cycle" in e.message.lower() for e in errors)


# --- Initial state tech prerequisites ---

def test_unlocked_tech_missing_prerequisite(valid_config):
    # Give a faction tech_fortification without tech_metallurgy
    fs = valid_config["initial_state"]["faction_states"][1]  # elves
    fs["unlocked_techs"].append("tech_fortification")
    errors = validate_world_config(valid_config)
    assert any("prérequis" in e.message for e in errors)


# --- Black swan rules ---

def test_black_swan_without_severity(valid_config):
    bsw = next(e for e in valid_config["event_pool"] if e["is_black_swan"])
    del bsw["severity"]
    errors = validate_world_config(valid_config)
    assert any("severity" in e.message for e in errors)


def test_non_black_swan_with_cascade(valid_config):
    evt = next(e for e in valid_config["event_pool"] if not e["is_black_swan"])
    evt["cascade"] = [{"event": "evt_migration", "probability": 0.5}]
    errors = validate_world_config(valid_config)
    assert any("cascade" in e.message.lower() for e in errors)
