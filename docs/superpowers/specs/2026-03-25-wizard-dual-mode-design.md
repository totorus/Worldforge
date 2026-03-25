# Wizard Dual Mode — Design Spec

## Objectif

Modifier le wizard de création de monde pour proposer deux approches dès le premier message de Kimi :
- **Mode guidé** : création détaillée en 11 étapes conversationnelles (comportement actuel, inchangé)
- **Mode surprise** : l'utilisateur donne un genre + des envies en texte libre, Kimi génère tout le reste de manière autonome. Le joueur découvrira le monde en jeu via le MJ IA.

Ajouter un bouton de régénération sur la page WorldView pour relancer la création du JSON sans repasser par le wizard.

## Contexte

WorldForge génère des bases de données de mondes fictifs destinées à alimenter une interface de JDR automatisée par IA. Un MJ IA s'appuie sur ces données pour créer des scénarios dynamiques. Le mode surprise existe pour les joueurs qui veulent une découverte totale en jeu.

## Flux conversationnel

### Premier message de Kimi (remplace le greeting actuel)

Kimi se présente et propose les deux modes de manière naturelle et conversationnelle (pas de mode robotique — une vraie conversation entre deux humains). Exemple de ton :

> "Salut ! Alors, tu viens créer un monde... j'adore ce moment. On a deux façons de faire ça ensemble.
>
> Soit on prend le temps — je te pose des questions sur tout, les paysages, les peuples, la magie, les conflits... tu me guides et je construis autour de tes idées.
>
> Soit tu me fais confiance — tu me dis juste quel genre d'univers te fait rêver, et je m'occupe de tout. Tu découvriras le monde en jouant, sans rien savoir à l'avance. C'est le mode aventurier.
>
> Qu'est-ce qui te tente ?"

Le system prompt de Kimi est modifié pour produire ce genre de greeting. Les instructions existantes (tutoiement, ton de conteur passionné, 3-5 phrases, français, pas de spoilers) restent en vigueur.

**Message déclencheur** : le message utilisateur injecté par `start_wizard` (actuellement `"Commence le wizard. Demande-moi quel genre de monde je veux créer."`) est remplacé par `"Commence la conversation."` pour laisser le system prompt piloter le greeting sans conflit d'instructions.

### Mode guidé (inchangé)

Si l'utilisateur choisit le mode guidé, le wizard continue exactement comme aujourd'hui : 11 étapes conversationnelles, barre de progression 11 points, bouton "Créer le monde" visible à partir de l'étape 8.

### Mode surprise

Si l'utilisateur choisit le mode surprise, Kimi pose 2 questions courtes dans un ton naturel :

1. **Genre** : "Quel genre de monde t'attire ?" (fantasy, sci-fi, post-apo, steampunk, etc.)
2. **Envies** : "Une envie particulière, un thème, une ambiance ?" (texte libre — le joueur peut dire "non", "des pirates", "quelque chose de sombre", etc.)

Après la 2e réponse, Kimi envoie un message de transition naturel (ex: "Parfait, laisse-moi travailler...") et la génération se lance automatiquement en background.

## Génération background et progression

### Lancement

Quand le mode surprise a collecté les réponses :

1. Le backend crée une tâche via le `task_manager` existant (même pattern que simulation/narration)
2. La tâche appelle Kimi pour générer le JSON complet (comme `finalize` actuel mais avec un prompt adapté au mode surprise)
3. Auto-repair + validation (couches existantes inchangées)
4. Sauvegarde en DB
5. La tâche écrit le message final de Kimi et met à jour `session.current_step = 4` dans la session (via `async_session`, même pattern que les background tasks de simulation/narration qui écrivent dans `World`)

### Messages immersifs de progression

Pendant la génération, des messages pré-définis (pas générés par Kimi) sont envoyés via un **nouvel event type WebSocket `wizard_progress`**. Le payload est :

```json
{
  "type": "wizard_progress",
  "session_id": "...",
  "message": "Je dessine les contours du monde...",
  "step": 3
}
```

Messages thématiques envoyés à intervalles réguliers, qui ne spoilent rien du contenu réel :

- "Je dessine les contours du monde..."
- "Des civilisations prennent forme..."
- "Les alliances et rivalités se nouent..."
- "L'histoire s'écrit, siècle après siècle..."
- "Les dernières touches..."

Ces messages sont **aussi persistés** dans `session.messages` (en tant que messages assistant) par la tâche background, pour qu'ils soient visibles lors d'une reprise de session.

Le frontend écoute les events `wizard_progress` sur la page Wizard et les affiche comme des messages assistant dans le chat en temps réel.

### Message final

Une fois la génération terminée et validée, la tâche background :
1. Appelle Kimi pour un message de conclusion naturel (ex: "Ton monde est né. Tout est en place — à toi de le découvrir.")
2. Persiste ce message dans `session.messages`
3. Met à jour `session.current_step = 4` (étape "Prêt" en mode surprise)
4. Met à jour `world.status = "configured"` et `world.config`
5. Envoie un event WebSocket `wizard_complete` avec le `world_id`

```json
{
  "type": "wizard_complete",
  "session_id": "...",
  "world_id": "...",
  "world_name": "..."
}
```

Le frontend affiche le bouton "Découvrir le monde" quand il reçoit `wizard_complete` ou quand l'historique retourne un `generation_status == "completed"`.

### Gestion des erreurs

En cas d'échec de génération ou de validation :
- La tâche background persiste un message d'erreur dans `session.messages`
- Un event WebSocket `wizard_error` est envoyé : `{"type": "wizard_error", "session_id": "...", "error": "..."}`
- Le frontend affiche le message + un bouton "Réessayer" qui rappelle `POST /{session_id}/generate`

### Reprise de session

L'utilisateur peut quitter la page et revenir à tout moment :

- La session wizard a un champ `mode` (`null` | `"guided"` | `"surprise"`) et un `generation_task_id` (string nullable) pour le job background
- `GET /wizard/{session_id}/history` retourne les champs supplémentaires :

```json
{
  "session_id": "...",
  "world_id": "...",
  "messages": [...],
  "step": 3,
  "status": "active",
  "mode": "surprise",
  "generation_task_id": "task_xyz",
  "generation_status": "running" | "completed" | "failed" | null
}
```

`generation_status` est résolu au moment du GET : si `generation_task_id` est non-null, le backend interroge le `task_manager` pour obtenir le statut. **Si le task_id n'est pas trouvé dans le task_manager** (ex: redémarrage serveur), le statut est déduit de l'état de la session : si `world.status == "configured"` et `world.config` est non-null → `"completed"`, sinon → `"failed"`.

- **Tâche en cours** : les messages déjà émis sont affichés (persistés en DB), reconnexion WebSocket pour les events `wizard_progress` suivants
- **Tâche terminée** : tous les messages + bouton "Découvrir le monde"
- **Tâche échouée** : messages + erreur + bouton "Réessayer"

## Barre de progression

### Mode guidé

Inchangée : 11 étapes (Genre, Ambiance, Géographie, Factions, Ressources, Pouvoirs, Événements, Personnages, Départ, Durée, Récap).

### Mode surprise

Barre adaptée à 4 étapes avec son propre domaine de valeurs (1-4, indépendant du 1-11 du mode guidé) :

1. **Genre** (step 1)
2. **Envies** (step 2)
3. **Génération** (step 3 — reste active pendant toute la phase background)
4. **Prêt** (step 4 — positionné par la tâche background quand la génération est terminée)

Le frontend choisit quelle barre afficher selon `session.mode`. Tant que `mode` est `null` (premier message), aucune barre n'est affichée.

## Détection du mode et des étapes

### Marqueur de mode

Le system prompt de Kimi inclut l'instruction d'ajouter un marqueur `[MODE:guided]` ou `[MODE:surprise]` dans sa réponse après le choix de l'utilisateur. Ce marqueur est strippé à l'affichage (même logique que `Étape N/11` actuellement).

### Refactoring de `_detect_step()`

`_detect_step()` est refactoré pour retourner un tuple `(step: int | None, mode: str | None)` au lieu d'un simple int. L'appelant dans `send_message` se charge de persister les deux valeurs sur la session :

```python
step, mode = _detect_step(response_text, current_step, current_mode)
if mode:
    session.mode = mode
if step:
    session.current_step = step
```

### Progression en mode surprise

En mode surprise, Kimi utilise le marqueur `Étape N/4` (au lieu de `Étape N/11`). `_detect_step()` détecte le dénominateur pour valider la cohérence avec le mode :
- Mode `null` ou `guided` : `Étape N/11`
- Mode `surprise` : `Étape N/4`

### Garde sur l'endpoint `/generate`

L'endpoint `POST /{session_id}/generate` vérifie les préconditions :
- `session.mode == "surprise"`
- `session.current_step >= 3` (les 2 questions ont été posées)
- `session.generation_task_id` est null ou la tâche précédente a échoué (pas de double lancement)

Sinon : HTTP 409 Conflict.

## Régénération depuis WorldView

### Bouton

Un bouton "Régénérer le monde" est ajouté sur la page WorldView, visible quel que soit le statut du monde.

### Avertissement

Si le monde a un statut avancé (`simulated`, `narrated`, `exported`), un dialogue de confirmation avertit que la simulation, narration et/ou export seront perdus. Le nettoyage est côté DB uniquement — les pages Bookstack éventuellement créées ne sont pas supprimées automatiquement (nettoyage manuel si nécessaire, hors scope de cette feature).

### Comportement

`POST /worlds/{world_id}/regenerate` — tâche background (pas synchrone, la génération prend 10-30s) :

1. Retrouve la `WizardSession` associée au monde
2. Lance une tâche background qui :
   - Appelle Kimi pour regénérer le JSON (comme `finalize`, à partir de la conversation wizard complète)
   - Auto-repair + validation
   - Sauvegarde `world.config`, remet `world.status = "configured"`
   - Efface `world.timeline`, `world.narrative_blocks`, `world.bookstack_mapping` (→ `null`)
3. Retourne un `task_id` au frontend
4. Le frontend affiche un spinner/état de progression et rafraîchit la page WorldView quand la tâche est terminée (via `task_manager` WebSocket events existants)

## Modifications par fichier

### Backend

| Fichier | Modification |
|---------|-------------|
| `app/services/wizard_prompt.py` | System prompt modifié : greeting avec choix de mode, instructions mode surprise (2-3 questions, ne rien révéler, marqueurs `[MODE:...]` et `Étape N/4`) |
| `app/routers/wizard.py` | `start_wizard` : message déclencheur changé ; `_detect_step()` retourne `(step, mode)` ; nouvel endpoint `POST /{session_id}/generate` (background, avec gardes) ; `history` retourne `mode`, `generation_task_id`, `generation_status` ; nouveaux events WebSocket `wizard_progress`, `wizard_complete`, `wizard_error` |
| `app/routers/worlds.py` | Nouvel endpoint `POST /{world_id}/regenerate` (background task) |
| `app/models/wizard_session.py` | Ajout colonnes `mode` (string nullable) et `generation_task_id` (string nullable) |
| Migration Alembic | Nouvelle migration pour les colonnes `mode` et `generation_task_id` |

### Frontend

| Fichier | Modification |
|---------|-------------|
| `src/pages/Wizard.jsx` | Gestion du champ `mode` ; écoute events WebSocket `wizard_progress`/`wizard_complete`/`wizard_error` ; en mode surprise : lancement auto de `generate` après step 3, bouton "Découvrir le monde" sur `wizard_complete` ou `generation_status == "completed"` |
| `src/components/WizardChat.jsx` | Barre de progression conditionnelle (4 étapes si mode surprise, 11 si mode guidé, cachée si mode null) ; messages immersifs affichés comme messages assistant |
| `src/pages/WorldView.jsx` | Bouton "Régénérer le monde" + dialogue de confirmation si statut avancé ; spinner pendant la régénération |
| `src/services/api.js` | Nouveaux appels : `wizard.generate(sessionId)`, `worlds.regenerate(worldId)` |

## Ce qui ne change PAS

- Le mode guidé (11 étapes conversationnelles)
- L'auto-repair et la validation JSON
- Le schema `world_config.json`
- Le simulateur, la narration, l'export
- Le `task_manager` (réutilisé tel quel, nouveaux event types ajoutés au WebSocket)
