# app/narrator/registry.py
"""EntityRegistry — tracks all known entities across pipeline steps for context propagation."""

import logging

logger = logging.getLogger("worldforge.narrator.registry")


class EntityRegistry:
    """Lightweight registry of all named entities in the world.

    Fed initially from config, then enriched after each pipeline step.
    Provides a compact text summary injectable into LLM prompts.
    """

    def __init__(self):
        self._entities: dict[str, set[str]] = {
            "factions": set(),
            "regions": set(),
            "characters": set(),
            "organizations": set(),
            "places": set(),
            "artifacts": set(),
            "creatures": set(),
            "other": set(),
        }
        self._era_names: list[str] = []
        self._era_ranges: list[tuple[str, int, int]] = []  # (name, start, end)

    def load_from_config(self, config: dict):
        """Seed registry from world config."""
        for fac in config.get("factions", []):
            name = fac.get("name", "")
            if name:
                self._entities["factions"].add(name)

        for reg in config.get("geography", {}).get("regions", []):
            name = reg.get("name", "")
            if name:
                self._entities["regions"].add(name)

        for tech in config.get("tech_tree", {}).get("nodes", []):
            name = tech.get("name", "")
            if name:
                self._entities["other"].add(name)

    def ingest_step(self, step_key: str, data):
        """Scan a pipeline step's output and register new entities."""
        if step_key == "eras" and isinstance(data, list):
            self._ingest_eras(data)
        elif step_key == "names" and isinstance(data, dict):
            self._ingest_names(data)
        elif step_key == "factions" and isinstance(data, list):
            self._ingest_factions(data)
        elif step_key == "regions" and isinstance(data, list):
            self._ingest_regions(data)
        elif step_key == "events" and isinstance(data, list):
            self._ingest_events(data)
        elif step_key == "characters" and isinstance(data, list):
            self._ingest_characters(data)
        elif step_key == "legends" and isinstance(data, list):
            self._ingest_legends(data)

    def _ingest_eras(self, eras: list):
        self._era_names = []
        self._era_ranges = []
        for era in eras:
            if not isinstance(era, dict):
                continue
            name = era.get("name", "")
            if name:
                self._era_names.append(name)
                self._era_ranges.append((
                    name,
                    era.get("start_year", 0),
                    era.get("end_year", 0),
                ))

    def _ingest_names(self, names: dict):
        for proper_name in names.values():
            if isinstance(proper_name, str) and proper_name:
                self._entities["characters"].add(proper_name)

    def _ingest_factions(self, factions: list):
        for fac in factions:
            if not isinstance(fac, dict):
                continue
            name = fac.get("name", "")
            if name:
                self._entities["factions"].add(name)
            # Scan text fields for new org/faction names mentioned
            self._scan_text_fields(fac)

    def _ingest_regions(self, regions: list):
        for reg in regions:
            if not isinstance(reg, dict):
                continue
            name = reg.get("name", "")
            if name:
                self._entities["regions"].add(name)
            self._scan_text_fields(reg)

    def _ingest_events(self, events: list):
        for evt in events:
            if not isinstance(evt, dict):
                continue
            title = evt.get("title", "")
            if title:
                self._entities["other"].add(title)
            # Capture faction names mentioned in events
            for fac in evt.get("involved_factions", []):
                if isinstance(fac, str) and fac:
                    self._entities["factions"].add(fac)

    def _ingest_characters(self, characters: list):
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = char.get("name", "")
            if name:
                self._entities["characters"].add(name)
            faction = char.get("faction", "")
            if isinstance(faction, str) and faction:
                self._entities["factions"].add(faction)

    def _ingest_legends(self, legends: list):
        for leg in legends:
            if not isinstance(leg, dict):
                continue
            title = leg.get("title", "")
            if title:
                self._entities["other"].add(title)
            for fac in leg.get("related_factions", []):
                if isinstance(fac, str) and fac:
                    self._entities["factions"].add(fac)
            for char in leg.get("related_characters", []):
                if isinstance(char, str) and char:
                    self._entities["characters"].add(char)

    def _scan_text_fields(self, item: dict):
        """Placeholder for future NLP-based entity detection in free text."""
        pass

    def compact_summary(self, max_chars: int = 800) -> str:
        """Produce a compact text summary of known entities for prompt injection.

        Returns a short block listing entity categories and names.
        """
        parts = []

        if self._era_ranges:
            era_strs = [f"{name} ({start}-{end})" for name, start, end in self._era_ranges]
            parts.append(f"Ères : {', '.join(era_strs)}")

        category_labels = {
            "factions": "Factions",
            "regions": "Régions",
            "characters": "Personnages",
            "organizations": "Organisations",
            "places": "Lieux",
            "artifacts": "Artefacts",
            "creatures": "Créatures",
        }

        for key, label in category_labels.items():
            names = sorted(self._entities.get(key, set()))
            if names:
                parts.append(f"{label} : {', '.join(names)}")

        summary = "\n".join(parts)

        # Truncate if too long — cut at last newline before limit
        if len(summary) > max_chars:
            cut = summary[:max_chars].rfind("\n")
            if cut > max_chars * 0.5:
                summary = summary[:cut]
            else:
                summary = summary[:max_chars]

        return summary

    def known_names(self) -> set[str]:
        """Return all known entity names as a flat set."""
        all_names = set()
        for names in self._entities.values():
            all_names.update(names)
        all_names.update(self._era_names)
        return all_names
