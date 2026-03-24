"""Tech tree unlock logic."""

import random

from app.simulator.types import WorldState, TechUnlock


def process_tech_unlocks(state: WorldState, rng: random.Random) -> list[TechUnlock]:
    """For each faction, attempt to unlock accessible techs. Returns list of unlocks this tick."""
    unlocks = []
    tech_map = {t["id"]: t for t in state.config["tech_tree"]["nodes"]}

    for faction in state.factions.values():
        unlocked_set = set(faction.unlocked_techs)

        for tech_id, tech in tech_map.items():
            if tech_id in unlocked_set:
                continue

            # Check prerequisites
            if not all(p in unlocked_set for p in tech["prerequisites"]):
                continue

            # Probability = (1 - unlock_difficulty) * power_affinity * 0.1
            prob = (1.0 - tech["unlock_difficulty"]) * faction.attributes.power_affinity * 0.1

            if rng.random() < prob:
                faction.unlocked_techs.append(tech_id)
                unlocked_set.add(tech_id)

                # Apply tech effects to faction attributes
                for attr, bonus in tech["effects"].items():
                    if attr in ("max_population_modifier", "avg_lifespan_modifier",
                                "defense_bonus", "attack_bonus"):
                        continue  # Special modifiers, not direct attribute changes
                    faction.attributes.apply_modifier(attr, bonus)

                # Apply lifespan modifier
                lifespan_mod = tech["effects"].get("avg_lifespan_modifier")
                if lifespan_mod:
                    faction.avg_lifespan = int(faction.avg_lifespan * lifespan_mod)

                unlocks.append(TechUnlock(faction_id=faction.id, tech_id=tech_id))

    return unlocks
