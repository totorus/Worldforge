"""Shared data structures for the simulator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Attributes:
    aggressiveness: float = 0.5
    cohesion: float = 0.5
    expansionism: float = 0.5
    power_affinity: float = 0.5
    fertility: float = 0.5
    adaptability: float = 0.5

    def apply_modifier(self, key: str, value: float):
        if hasattr(self, key):
            current = getattr(self, key)
            setattr(self, key, max(0.0, min(1.0, current + value)))

    def to_dict(self) -> dict:
        return {
            "aggressiveness": round(self.aggressiveness, 4),
            "cohesion": round(self.cohesion, 4),
            "expansionism": round(self.expansionism, 4),
            "power_affinity": round(self.power_affinity, 4),
            "fertility": round(self.fertility, 4),
            "adaptability": round(self.adaptability, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Attributes:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k)})


@dataclass
class Character:
    id: str
    faction_id: str
    role_id: str
    name_placeholder: str
    spawn_year: int
    duration_ticks: int
    impact: float
    attribute_modifiers: dict[str, float] = field(default_factory=dict)

    @property
    def end_year(self) -> int:
        return self.spawn_year + self.duration_ticks


@dataclass
class Relation:
    faction_a: str
    faction_b: str
    type: str  # alliance | neutral | rivalry
    intensity: float  # 0-1

    def involves(self, fac_id: str) -> bool:
        return fac_id in (self.faction_a, self.faction_b)

    def other(self, fac_id: str) -> str:
        return self.faction_b if fac_id == self.faction_a else self.faction_a

    def to_dict(self) -> dict:
        return {
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "type": self.type,
            "intensity": round(self.intensity, 4),
        }


@dataclass
class FactionState:
    id: str
    name: str
    governance: str
    avg_lifespan: int
    cultural_traits: list[str]
    attributes: Attributes
    population: int
    regions: list[str]
    unlocked_techs: list[str]
    active_characters: list[Character] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "population": self.population,
            "regions": list(self.regions),
            "attributes": self.attributes.to_dict(),
            "unlocked_techs": list(self.unlocked_techs),
        }


@dataclass
class RegionState:
    id: str
    name: str
    terrain: str
    habitability: float
    max_population: int
    resources: list[str]
    connections: list[dict]  # [{target, traversal_difficulty}]


@dataclass
class EventRecord:
    event_id: str
    involved_factions: list[str]
    involved_regions: list[str]
    outcome: dict

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "involved_factions": self.involved_factions,
            "involved_regions": self.involved_regions,
            "outcome": self.outcome,
        }


@dataclass
class CharacterEvent:
    type: str  # spawn | retire
    faction_id: str
    role: str
    name_placeholder: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "faction_id": self.faction_id,
            "role": self.role,
            "name_placeholder": self.name_placeholder,
        }


@dataclass
class TechUnlock:
    faction_id: str
    tech_id: str

    def to_dict(self) -> dict:
        return {"faction_id": self.faction_id, "tech_id": self.tech_id}


@dataclass
class TickResult:
    year: int
    events: list[EventRecord] = field(default_factory=list)
    tech_unlocks: list[TechUnlock] = field(default_factory=list)
    character_events: list[CharacterEvent] = field(default_factory=list)
    world_state: dict = field(default_factory=dict)  # snapshot at end of tick

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "events": [e.to_dict() for e in self.events],
            "tech_unlocks": [t.to_dict() for t in self.tech_unlocks],
            "character_events": [c.to_dict() for c in self.character_events],
            "world_state": self.world_state,
        }


@dataclass
class WorldState:
    """Mutable world state passed through the simulation loop."""
    config: dict  # original config (read-only reference)
    factions: dict[str, FactionState] = field(default_factory=dict)
    regions: dict[str, RegionState] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    active_characters: list[Character] = field(default_factory=list)
    trade_routes_active: bool = False
    year: int = 0

    def get_relation(self, fac_a: str, fac_b: str) -> Relation | None:
        for r in self.relations:
            if {r.faction_a, r.faction_b} == {fac_a, fac_b}:
                return r
        return None

    def get_adjacent_faction_pairs(self) -> list[tuple[str, str]]:
        """Return pairs of faction IDs that occupy connected regions."""
        pairs = set()
        # Build region -> factions mapping
        region_to_factions: dict[str, list[str]] = {}
        for fac in self.factions.values():
            for reg_id in fac.regions:
                region_to_factions.setdefault(reg_id, []).append(fac.id)

        # Check connections
        for region in self.regions.values():
            facs_here = region_to_factions.get(region.id, [])
            for conn in region.connections:
                facs_there = region_to_factions.get(conn["target"], [])
                for fa in facs_here:
                    for fb in facs_there:
                        if fa != fb:
                            pair = tuple(sorted((fa, fb)))
                            pairs.add(pair)
        return list(pairs)

    def snapshot(self) -> dict:
        return {
            "factions": [f.to_dict() for f in self.factions.values()],
            "relations": [r.to_dict() for r in self.relations],
        }
