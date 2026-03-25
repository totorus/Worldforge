# Entity Extraction & Lore Enrichment — Design Spec

**Date:** 2026-03-25

## Problem

The narrator generates narrative text that mentions invented entities (locations, creatures, characters, resources, organizations, artifacts) without creating dedicated sheets for them. Additionally, entire lore dimensions are missing: races/peoples, cosmogonies, fauna, flora, bestiary.

## Solution

### 1. New Narrator Step: Entity Extraction (after legends, before coherence)

**Detection** (Kimi K2.5): Scan all narrative blocks for unique invented proper nouns that don't have their own sheet. Classify each entity by type.

**Generation** (Mistral Small Creative): Generate a dedicated sheet for each detected entity, using a type-specific template.

**Depth iteration**: Sheets generated at level N are scanned for new entities at level N+1. Max 4 levels.

**Kimi constraint**: No parallel API calls to Moonshot. All Kimi calls must be sequential.

### 2. Entity Types & Sheet Templates

| Type | Fields | Generation |
|---|---|---|
| Race/Peuple | Description physique, espérance de vie, factions associées, régions d'habitat, philosophie/valeurs, rapport magie, rapport technologie, relations inter-races, traits culturels | By detection |
| Cosmogonie | Rattachée à une race. Création du monde, divinités/forces primordiales, naissance de la race, valeurs fondatrices | Automatic per race |
| Légende | Récit, type, peuples rattachés, portée (unique/partagée). Si partagée: tronc commun + variantes par peuple | By detection |
| Faune | Description, habitat, comportement, dangerosité, lien magie, rareté. Only if world-specific | By detection |
| Flore | Description, habitat, propriétés, usages, rareté. Only if world-specific | By detection |
| Bestiaire | Description, habitat, pouvoirs, dangerosité, origine, faiblesses, légendes associées | By detection |
| Lieu notable | Description, région, histoire, importance, statut (existant/ruines/légendaire/localisation perdue/disparu) | By detection |
| Ressource | Description, rareté, propriétés, localisation, usages | By detection |
| Organisation | Description, fondation, objectifs, structure, membres notables, influence | By detection |
| Artefact | Description, origine, pouvoirs, localisation, histoire | By detection |
| Personnage historique | Biographie, description physique, rôle, faction, race, époque, naissance, mort, statut actuel (vivant/mort/disparu/inconnu), faits marquants, héritage | By detection |

### 3. Revised Pipeline

```
SIMULATOR (Python)
1. simulation → timeline
2. programmatic validator (assertions/invariants)

NARRATOR (LLM)
3.  era_splitting              (Kimi)
4.  naming                     (Mistral Small 4)
5.  faction_sheets             (Mistral Creative)
6.  region_sheets              (Mistral Creative)
7.  event_narratives           (Mistral Creative)
8.  character_bios             (Mistral Creative)
9.  legends                    (Mistral Creative)
10. entity_extraction          (Kimi detect → Mistral Creative generate, 4 levels max)
11. coherence_check            (Kimi) → score 0.0–1.0
    └─ if score < 0.75: auto-correct faulty blocks (max 3 iterations)
```

### 4. Coherence Auto-Correction Loop

- Check coherence → score + issues
- If score < 0.75: identify faulty blocks, re-narrate them with issues as context
- Max 3 iterations
- If still < 0.75 after 3 passes: export anyway + warning in annexes

### 5. Bookstack Export — New Chapters

Added chapters: Races & Peuples, Cosmogonies, Faune, Flore, Bestiaire, Lieux notables, Ressources, Organisations, Artefacts.

### 6. Cross-References

Extend existing `_inject_cross_references()` mechanism to cover all new entity pages. Every mention of an entity with a page becomes a hyperlink.

### 7. Simulator Validator

Post-simulation Python assertions:
- Dead characters cannot act
- Destroyed factions cannot declare war
- Tech prerequisites must be met before unlock
- Population cannot be negative
- Faction must hold at least one region or be marked destroyed
