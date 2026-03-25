# Corrections Timeline, Export et Extraction d'Entités — Design Spec

## Objectif

Corriger 5 problèmes liés à l'affichage de la timeline, l'export Bookstack, et l'extraction d'entités. Ces problèmes proviennent de décalages entre la structure de données du simulateur et ce que le frontend/export/narrateur attendent.

## Contexte

Sur Velmorath (7 factions, 6 régions, 800 ans, 80 ticks, 114 événements timeline, 48 blocs narratifs d'événements) :
- La timeline ne s'affiche pas du tout dans le frontend
- Toutes les fiches d'événements sont vides dans le wiki Bookstack
- Le tech_tree complet est exporté au lieu des seules techs déverrouillées
- L'extraction d'entités est trop pauvre (1 race, 1 créature, 0 faune, 0 flore pour un monde de 7 factions)
- L'export crée des chapitres sans indiquer s'ils sont peuplés ou vides

## 1. Fix du TimelineViewer (frontend)

### Problème

`Timeline.jsx` passe `data` (= `{world_id, timeline}`) au composant `TimelineViewer` qui attend directement l'objet timeline. De plus, le composant attend des champs inexistants dans la structure du simulateur.

Structure réelle d'un tick :
```json
{
  "year": 10,
  "events": [
    {
      "event_id": "evt_marée_de_souvenirs",
      "outcome": { "faction": "fac_veilthorn", "effects_applied": {} },
      "involved_regions": ["reg_veilthorn"],
      "involved_factions": ["fac_veilthorn"]
    }
  ],
  "world_state": { "factions": [...] }
}
```

Le viewer cherche `type`/`category`, `name`/`title`, `description` pour les événements — ces champs n'existent pas sous cette forme dans les events. En revanche, `tech_unlocks` et `character_events` **existent bien** dans les ticks (générés par `process_tech_unlocks` et `process_characters` dans `engine.py`).

### Corrections

**`Timeline.jsx`** : passer `data.timeline` au composant au lieu de `data`.

**`TimelineViewer.jsx`** :
- Résoudre le nom lisible de l'événement via `event_id` (en utilisant les noms narratifs du monde, passés en prop ou via un mapping `event_pool` → noms narratifs)
- Afficher les factions impliquées (`involved_factions`) et régions (`involved_regions`)
- Conserver `tech_unlocks` et `character_events` dans les stats et l'affichage détaillé (ces champs existent dans les ticks)
- Retirer les filtres par catégorie (`type`/`category` n'existent pas dans les events)
- Passer le `config.event_pool` ou les `narrative_blocks.names` en prop pour résoudre les IDs en noms lisibles

## 2. Fix des fiches narratives d'événements dans l'export

### Problème

Le formatter `format_era_page` lit déjà les bons champs (`title`, `narrative`, `consequences_narrative`, `involved_factions`). Le vrai problème est dans `pipeline.py` : les événements narratifs sont regroupés par `era` (`narr_events_by_era`) et matchés avec les ères par nom exact. Or le LLM génère des noms d'ères incohérents dans les événements.

Données de Velmorath : 5 ères définies mais les événements utilisent **19 noms d'ères différents**. Seuls 3-4 matchent exactement. Les autres (ex: "L'Âge des Ombres Cachées", "Le Crépuscule des Racines (710–800)") ne correspondent à aucune ère et sont perdus.

### Corrections

**`pipeline.py`** : remplacer le match exact par nom (`narr_events_by_era.get(era_name, [])` ligne 273) par un matching en cascade :

1. **Match exact** : le champ `era` de l'événement correspond exactement au `name` de l'ère → assigné
2. **Match par inclusion** : le nom de l'ère est contenu dans le champ `era` de l'événement (ou vice-versa) → assigné à la première ère trouvée
3. **Match par année** : si l'événement a un champ `year`, l'assigner à l'ère dont la plage `start_year`–`end_year` le contient (même logique que `_group_events_by_era()` lignes 89-107 qui fait déjà du year-range matching pour les événements simulateur, mais pas pour les événements narratifs)
4. **Fallback** : événements orphelins regroupés dans une section "Événements non classés"

Créer une fonction helper `_match_event_to_era(event, eras)` qui implémente cette cascade, utilisée pour le regroupement des événements narratifs.

**Pas de changement dans `formatters.py`** — les champs sont déjà correctement lus.

## 3. Technologies : exporter uniquement les déverrouillées

### Problème

L'export crée une fiche pour chaque technologie du `tech_tree` dans la config. Les techs verrouillées (jamais découvertes) n'ont aucun intérêt. Le `tech_tree` complet n'a pas sa place en BDD non plus — il sert au simulateur pendant l'exécution.

### Règle

On exporte toutes les techs **déverrouillées** (= utilisées par au moins une faction), que ce soit dans l'état initial ou découvertes pendant la simulation. Les techs verrouillées sont ignorées.

### Corrections

**Export (`pipeline.py`)** :
- Lire le `world_state` du dernier tick de la timeline : chaque faction a ses `unlocked_techs` qui représentent l'état cumulé final
- Faire l'union de toutes les `unlocked_techs` de toutes les factions du dernier tick
- Ne créer des fiches que pour ces techs
- Résoudre les détails de chaque tech (nom, description, etc.) via le `tech_tree` de la config

**Pas de suppression du tech_tree de la config** pour l'instant — le simulateur en a besoin à l'exécution. Mais l'export ne doit pas le parcourir en entier.

## 4. Extraction d'entités par ère

### Problème

L'extraction actuelle envoie tout le texte narratif en un seul appel à Kimi, qui rate la majorité des entités. Pour Velmorath : 1 race, 0 faune, 0 flore, 1 créature — alors qu'il y a 7 factions, 6 régions, 800 ans d'histoire riche.

### Nouvelle approche

Découper l'extraction par ère. Pour chaque ère chronologiquement :

1. **Contexte** : entités déjà détectées dans les ères précédentes (noms + types)
2. **Input** : blocs narratifs de l'ère courante (événements, personnages, légendes de cette période) + données structurées dérivées de la timeline. Agrégation per-ère :
   - Filtrer les ticks dont `year` ∈ [`start_year`, `end_year`] de l'ère
   - Factions actives : union des noms de factions dans `world_state.factions` des ticks filtrés
   - Régions concernées : union des `involved_regions` de tous les `events` des ticks filtrés
   - Techs déverrouillées : union des `unlocked_techs` de toutes les factions dans le dernier tick de la tranche
3. **Détection** : appel Kimi (séquentiel — contrainte Moonshot API, un seul appel à la fois). Kimi cherche les nouvelles entités dans cette tranche — races, créatures, faune, flore, lieux, ressources, organisations, artefacts, personnages historiques, légendes
4. **Génération des fiches** : pour chaque nouvelle entité détectée, générer la fiche via Mistral Creative (appels séquentiels via OpenRouter). Séquence : détection Kimi ère 1 → fiches Mistral ère 1 → détection Kimi ère 2 → fiches Mistral ère 2 → ...
5. **Accumulation** : passer à l'ère suivante avec le pool d'entités enrichi. La structure de sortie reste identique à l'actuelle (listes plates `entities_faune`, `entities_flore`, etc.) — les entités de toutes les ères sont fusionnées dans les mêmes listes. Le contrat avec `pipeline.py` (qui lit ces clés) ne change pas.

**Volume d'appels LLM** : 1 appel de détection Kimi par ère (ex: 5 ères = 5 appels de détection) + 1 appel Mistral Creative par fiche d'entité. C'est comparable au système actuel (4 profondeurs × 1 détection = 4 appels de détection + N fiches). Le nombre de fiches dépend de la richesse du monde, pas de l'architecture.

**Avantages :**
- Moins de texte par appel → meilleure précision
- Entités liées à leur époque
- Cumulatif : Kimi voit ce qui existe déjà et peut compléter
- Les personnages déjà narratés dans `characters` sont inclus dans le contexte structurel → ils seront naturellement détectés

**Prompt de détection** : inclure des indications de volume attendu ("un monde avec N factions et M régions devrait avoir au minimum X races, Y créatures, Z lieux notables...") pour pousser Kimi à ratisser large.

### Fichiers impactés

- `backend/app/narrator/entity_extraction.py` : refonte de `run_entity_extraction()` pour le découpage par ère
- `backend/app/narrator/pipeline.py` : pas de changement d'interface — l'étape 8 appelle toujours `run_entity_extraction()`, seul le contenu change

### Test

Après implémentation, tester uniquement l'extraction d'entités sur Velmorath :
- Script Python lancé dans le container backend
- Compare les résultats avant/après (nombre d'entités par type)
- Corriger si les résultats sont insuffisants avant de passer à la suite

## 5. Chapitres Bookstack avec compteur de fiches

### Problème

L'export crée systématiquement tous les chapitres (Faune, Flore, Bestiaire, etc.) même quand ils sont vides. Pas moyen de voir d'un coup d'œil ce qui est peuplé.

### Correction

Les chapitres sont créés **avant** les pages (lignes 203-207 de `pipeline.py`), donc le nombre de pages n'est pas connu à la création. Solution en deux passes :

1. **Création des chapitres** : inchangée (description originale)
2. **Après création de toutes les pages** : compter les pages créées par chapitre, puis mettre à jour la description de chaque chapitre avec le compteur

**`bookstack_client.py`** : ajouter une méthode `update_chapter(chapter_id, description)` qui fait un `PUT /api/chapters/{id}`.

**`pipeline.py`** : après la boucle de création de pages, compter les pages par `chapter_id` dans `pages_created`, puis appeler `update_chapter` pour chaque chapitre avec la description enrichie.

Exemple : `"Animaux notables du monde — 3 fiches"` ou `"Animaux notables du monde — 0 fiches"`.

Tous les chapitres sont toujours créés — seule la description est mise à jour après coup pour indiquer le volume.

## Ce qui ne change PAS

- Le simulateur (moteur procédural)
- Le narrateur (étapes 1-7 : nommage, ères, factions, régions, événements, personnages, légendes)
- La cohérence auto-fix (étape 9)
- Le schema `world_config.json`
- Le wizard
