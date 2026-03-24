"""Tests for the simulation engine."""

import json
from pathlib import Path

import pytest

from app.simulator.engine import run_simulation
from app.simulator.types import Attributes

EXAMPLE_PATH = Path(__file__).resolve().parent.parent.parent / "world_config_example.json"


@pytest.fixture
def config():
    return json.loads(EXAMPLE_PATH.read_text())


# --- Full simulation ---

def test_full_simulation_runs(config):
    timeline = run_simulation(config)
    assert timeline["seed"] == 42
    assert len(timeline["ticks"]) == config["meta"]["simulation_years"]
    assert "world_id" in timeline
    assert "config_hash" in timeline


def test_simulation_produces_events(config):
    timeline = run_simulation(config)
    all_events = []
    for tick in timeline["ticks"]:
        all_events.extend(tick["events"])
    # Over 500 years, we should have many events
    assert len(all_events) > 10


def test_simulation_produces_characters(config):
    timeline = run_simulation(config)
    all_chars = []
    for tick in timeline["ticks"]:
        all_chars.extend(tick["character_events"])
    assert len(all_chars) > 0


def test_simulation_produces_tech_unlocks(config):
    timeline = run_simulation(config)
    all_techs = []
    for tick in timeline["ticks"]:
        all_techs.extend(tick["tech_unlocks"])
    assert len(all_techs) > 0


def test_simulation_world_state_per_tick(config):
    timeline = run_simulation(config)
    for tick in timeline["ticks"]:
        ws = tick["world_state"]
        assert "factions" in ws
        assert "relations" in ws
        assert len(ws["factions"]) >= 2  # At least 2 factions survive


def test_population_grows_over_time(config):
    config["meta"]["simulation_years"] = 50
    timeline = run_simulation(config)
    initial_pop = sum(
        fs["starting_population"]
        for fs in config["initial_state"]["faction_states"]
    )
    final_pop = sum(
        f["population"]
        for f in timeline["ticks"][-1]["world_state"]["factions"]
    )
    # Population should change (grow or lose due to events)
    assert final_pop != initial_pop


# --- Reproducibility ---

def test_same_seed_same_result(config):
    t1 = run_simulation(config)
    t2 = run_simulation(config)
    # Same seed should produce identical results
    assert len(t1["ticks"]) == len(t2["ticks"])
    for tick1, tick2 in zip(t1["ticks"], t2["ticks"]):
        assert tick1["year"] == tick2["year"]
        assert len(tick1["events"]) == len(tick2["events"])


def test_different_seed_different_result(config):
    t1 = run_simulation(config)
    config["meta"]["seed"] = 999
    t2 = run_simulation(config)
    # Different seeds should (very likely) produce different events
    events1 = [e["event_id"] for t in t1["ticks"] for e in t["events"]]
    events2 = [e["event_id"] for t in t2["ticks"] for e in t["events"]]
    assert events1 != events2


# --- Tick duration ---

def test_tick_duration_5_years(config):
    config["meta"]["tick_duration_years"] = 5
    config["meta"]["simulation_years"] = 100
    timeline = run_simulation(config)
    assert len(timeline["ticks"]) == 20
    assert timeline["ticks"][0]["year"] == 5
    assert timeline["ticks"][-1]["year"] == 100


# --- Attributes ---

def test_attributes_stay_in_bounds(config):
    timeline = run_simulation(config)
    for tick in timeline["ticks"]:
        for fac in tick["world_state"]["factions"]:
            attrs = fac["attributes"]
            for key, val in attrs.items():
                assert 0.0 <= val <= 1.0, f"{fac['id']}.{key} = {val} out of bounds at year {tick['year']}"


# --- Types unit tests ---

def test_attributes_clamp():
    a = Attributes(aggressiveness=0.9)
    a.apply_modifier("aggressiveness", 0.5)
    assert a.aggressiveness == 1.0
    a.apply_modifier("aggressiveness", -2.0)
    assert a.aggressiveness == 0.0
