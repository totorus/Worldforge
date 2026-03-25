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

### Messages immersifs de progression

Pendant la génération, des messages pré-définis (pas générés par Kimi) sont envoyés dans le chat via WebSocket à intervalles réguliers. Ils sont thématiques et ne spoilent rien du contenu réel :

- "Je dessine les contours du monde..."
- "Des civilisations prennent forme..."
- "Les alliances et rivalités se nouent..."
- "L'histoire s'écrit, siècle après siècle..."
- "Les dernières touches..."

Ces messages sont stockés dans la session comme des messages assistant normaux (persistés en DB).

### Message final

Une fois la génération terminée et validée, un vrai message Kimi est généré (appel LLM) pour conclure naturellement, par exemple : "Ton monde est né. Tout est en place — à toi de le découvrir."

Le bouton "Découvrir le monde" apparaît alors.

### Gestion des erreurs

En cas d'échec de génération ou de validation :
- Un message d'erreur clair est affiché dans le chat
- Un bouton "Réessayer" permet de relancer la génération avec les mêmes paramètres

### Reprise de session

L'utilisateur peut quitter la page et revenir à tout moment :

- La session wizard a un champ `mode` (`null` | `"guided"` | `"surprise"`) et un `task_id` optionnel pour le job background
- `GET /wizard/{session_id}/history` retourne l'historique des messages + l'état de la tâche background
- **Tâche en cours** : les messages déjà émis sont affichés, reconnexion WebSocket pour les suivants
- **Tâche terminée** : tous les messages + bouton "Découvrir le monde"
- **Tâche échouée** : messages + erreur + bouton "Réessayer"

## Barre de progression

### Mode guidé

Inchangée : 11 étapes (Genre, Ambiance, Géographie, Factions, Ressources, Pouvoirs, Événements, Personnages, Départ, Durée, Récap).

### Mode surprise

Barre adaptée à 4 étapes :

1. **Genre**
2. **Envies**
3. **Génération** (reste active pendant toute la phase background)
4. **Prêt**

## Détection du mode

Le system prompt de Kimi inclut l'instruction d'ajouter un marqueur `[MODE:guided]` ou `[MODE:surprise]` dans sa réponse après le choix de l'utilisateur. Ce marqueur est strippé à l'affichage (même logique que `Étape N/11` actuellement).

`_detect_step()` dans le router wizard est étendu pour :
- Détecter le marqueur de mode via regex
- Mettre à jour `session.mode`
- En mode surprise : la progression passe de step 1 (choix) → step 2 (genre) → step 3 (envies) → step 11 (génération)

## Régénération depuis WorldView

### Bouton

Un bouton "Régénérer le monde" est ajouté sur la page WorldView, visible quel que soit le statut du monde.

### Avertissement

Si le monde a un statut avancé (`simulated`, `narrated`, `exported`), un dialogue de confirmation avertit que la simulation, narration et/ou export seront perdus.

### Comportement

1. Appel `POST /wizard/{session_id}/regenerate` (ou réutilisation de `finalize` + `validate`)
2. Le backend relance la génération JSON à partir de la conversation wizard existante (mode guidé ou surprise)
3. Auto-repair + validation
4. Sauvegarde en DB, statut remis à `"configured"`, suppression des données de simulation/narration/export
5. La page WorldView se rafraîchit avec le nouveau monde

## Modifications par fichier

### Backend

| Fichier | Modification |
|---------|-------------|
| `app/services/wizard_prompt.py` | System prompt modifié : greeting avec choix de mode, instructions mode surprise (2-3 questions, ne rien révéler, marqueur `[MODE:...]`) |
| `app/routers/wizard.py` | Champ `mode` sur `WizardSession` ; `_detect_step()` étendu pour détecter le mode ; nouvel endpoint `POST /{session_id}/generate` pour génération background ; endpoint `POST /{session_id}/regenerate` pour régénération ; messages immersifs via WebSocket |
| `app/models/wizard_session.py` | Ajout colonne `mode` (string nullable) et `generation_task_id` (string nullable) |
| Migration Alembic | Nouvelle migration pour les colonnes `mode` et `generation_task_id` |

### Frontend

| Fichier | Modification |
|---------|-------------|
| `src/pages/Wizard.jsx` | Gestion du champ `mode` ; en mode surprise : lancement auto de la génération après 2e réponse, reconnexion WebSocket pour progression, bouton "Découvrir le monde" |
| `src/components/WizardChat.jsx` | Barre de progression adaptée (4 étapes en mode surprise vs 11 en mode guidé) ; messages immersifs affichés normalement |
| `src/pages/WorldView.jsx` | Bouton "Régénérer le monde" + dialogue de confirmation si données avancées |
| `src/services/api.js` | Nouveaux appels : `wizard.generate(sessionId)`, `wizard.regenerate(sessionId)` |

## Ce qui ne change PAS

- Le mode guidé (11 étapes conversationnelles)
- L'auto-repair et la validation JSON
- Le schema `world_config.json`
- Le simulateur, la narration, l'export
- Le `task_manager` et le système WebSocket (réutilisés tels quels)
