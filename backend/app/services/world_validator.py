"""World configuration validator.

Two layers:
1. JSON Schema validation (structure, types, patterns)
2. Business rules (referential integrity, bidirectional connections, tech cycles, etc.)
"""

import json
from collections import defaultdict
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "world_config.json"

_schema_cache = None


def _load_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(SCHEMA_PATH.read_text())
    return _schema_cache


class ValidationError:
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def dict(self):
        return {"field": self.field, "message": self.message}


def validate_world_config(config: dict) -> list[ValidationError]:
    """Validate a world config dict. Returns a list of errors (empty = valid)."""
    errors = []

    # --- Layer 1: JSON Schema ---
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(config):
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(ValidationError(path, err.message))

    if errors:
        return errors  # Stop here if structure is broken

    # --- Layer 2: Business rules ---
    errors.extend(_validate_referential_integrity(config))
    errors.extend(_validate_bidirectional_connections(config))
    errors.extend(_validate_tech_no_cycles(config))
    errors.extend(_validate_initial_state(config))
    errors.extend(_validate_cascade_references(config))

    return errors


def _validate_referential_integrity(config: dict) -> list[ValidationError]:
    """Check that all referenced IDs exist."""
    errors = []

    region_ids = {r["id"] for r in config["geography"]["regions"]}
    resource_ids = {r["id"] for r in config["resources"]}
    faction_ids = {f["id"] for f in config["factions"]}
    tech_ids = {t["id"] for t in config["tech_tree"]["nodes"]}
    event_ids = {e["id"] for e in config["event_pool"]}

    # Regions reference valid resources
    for region in config["geography"]["regions"]:
        for res_id in region["resources"]:
            if res_id not in resource_ids:
                errors.append(ValidationError(
                    f"geography.regions.{region['id']}.resources",
                    f"Ressource '{res_id}' référencée mais inexistante",
                ))

    # Region connections reference valid regions
    for region in config["geography"]["regions"]:
        for conn in region["connections"]:
            if conn["target"] not in region_ids:
                errors.append(ValidationError(
                    f"geography.regions.{region['id']}.connections",
                    f"Région cible '{conn['target']}' inexistante",
                ))

    # Tech prerequisites reference valid techs
    for tech in config["tech_tree"]["nodes"]:
        for prereq in tech["prerequisites"]:
            if prereq not in tech_ids:
                errors.append(ValidationError(
                    f"tech_tree.nodes.{tech['id']}.prerequisites",
                    f"Prérequis tech '{prereq}' inexistant",
                ))

    # Cascade events reference valid events
    for event in config["event_pool"]:
        for cascade in event.get("cascade", []):
            if cascade["event"] not in event_ids:
                errors.append(ValidationError(
                    f"event_pool.{event['id']}.cascade",
                    f"Événement en cascade '{cascade['event']}' inexistant",
                ))

    # initial_state references
    for fs in config["initial_state"]["faction_states"]:
        if fs["faction_id"] not in faction_ids:
            errors.append(ValidationError(
                f"initial_state.faction_states.{fs['faction_id']}",
                f"Faction '{fs['faction_id']}' inexistante",
            ))
        for reg_id in fs["starting_regions"]:
            if reg_id not in region_ids:
                errors.append(ValidationError(
                    f"initial_state.faction_states.{fs['faction_id']}.starting_regions",
                    f"Région '{reg_id}' inexistante",
                ))
        for tech_id in fs["unlocked_techs"]:
            if tech_id not in tech_ids:
                errors.append(ValidationError(
                    f"initial_state.faction_states.{fs['faction_id']}.unlocked_techs",
                    f"Tech '{tech_id}' inexistante",
                ))

    for rel in config["initial_state"]["initial_relations"]:
        for key in ("faction_a", "faction_b"):
            if rel[key] not in faction_ids:
                errors.append(ValidationError(
                    f"initial_state.initial_relations.{key}",
                    f"Faction '{rel[key]}' inexistante",
                ))

    for he in config["initial_state"].get("historical_events", []):
        for fac_id in he["involved_factions"]:
            if fac_id not in faction_ids:
                errors.append(ValidationError(
                    "initial_state.historical_events",
                    f"Faction '{fac_id}' inexistante dans un événement historique",
                ))

    return errors


def _validate_bidirectional_connections(config: dict) -> list[ValidationError]:
    """Connections between regions must be bidirectional."""
    errors = []
    connections = defaultdict(set)

    for region in config["geography"]["regions"]:
        for conn in region["connections"]:
            connections[region["id"]].add(conn["target"])

    for region in config["geography"]["regions"]:
        for conn in region["connections"]:
            target = conn["target"]
            if region["id"] not in connections.get(target, set()):
                errors.append(ValidationError(
                    f"geography.regions.{region['id']}.connections",
                    f"Connexion {region['id']} → {target} n'est pas bidirectionnelle "
                    f"({target} → {region['id']} manquante)",
                ))

    return errors


def _validate_tech_no_cycles(config: dict) -> list[ValidationError]:
    """Tech prerequisites must not form cycles."""
    errors = []
    prereqs = {t["id"]: t["prerequisites"] for t in config["tech_tree"]["nodes"]}

    def has_cycle(node_id: str, visited: set, path: set) -> bool:
        if node_id in path:
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        path.add(node_id)
        for prereq in prereqs.get(node_id, []):
            if has_cycle(prereq, visited, path):
                return True
        path.discard(node_id)
        return False

    visited = set()
    for tech_id in prereqs:
        if has_cycle(tech_id, visited, set()):
            errors.append(ValidationError(
                f"tech_tree.nodes.{tech_id}",
                "Cycle détecté dans les prérequis technologiques",
            ))

    return errors


def _validate_initial_state(config: dict) -> list[ValidationError]:
    """Unlocked techs must have their prerequisites also unlocked."""
    errors = []
    prereqs = {t["id"]: t["prerequisites"] for t in config["tech_tree"]["nodes"]}

    for fs in config["initial_state"]["faction_states"]:
        unlocked = set(fs["unlocked_techs"])
        for tech_id in fs["unlocked_techs"]:
            for prereq in prereqs.get(tech_id, []):
                if prereq not in unlocked:
                    errors.append(ValidationError(
                        f"initial_state.faction_states.{fs['faction_id']}.unlocked_techs",
                        f"Tech '{tech_id}' débloquée mais son prérequis '{prereq}' ne l'est pas",
                    ))

    return errors


def _validate_cascade_references(config: dict) -> list[ValidationError]:
    """Black swan events should have severity, non-black-swan should not have cascade."""
    errors = []

    for event in config["event_pool"]:
        if event["is_black_swan"] and "severity" not in event:
            errors.append(ValidationError(
                f"event_pool.{event['id']}",
                "Les événements black swan doivent avoir un champ 'severity'",
            ))
        if not event["is_black_swan"] and event.get("cascade"):
            errors.append(ValidationError(
                f"event_pool.{event['id']}",
                "Seuls les événements black swan peuvent avoir des cascades",
            ))

    return errors
