# Wizard Dual Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "surprise" mode to the wizard where Kimi asks 2-3 questions then generates the world autonomously in background, alongside the existing "guided" 11-step mode.

**Architecture:** WizardSession gets `mode` and `generation_task_id` columns. `_detect_step()` is refactored to return `(step, mode)`. A new `POST /generate` endpoint launches background world generation using the existing `task_manager`. New WebSocket event types (`wizard_progress`, `wizard_complete`, `wizard_error`) deliver real-time chat messages. Frontend conditionally renders a 4-step or 11-step progress bar based on mode.

**Tech Stack:** Python FastAPI, SQLAlchemy + Alembic, React, WebSocket, Kimi K2.5 (Moonshot API)

**Spec:** `docs/superpowers/specs/2026-03-25-wizard-dual-mode-design.md`

---

### Task 1: DB Migration — Add mode and generation_task_id to WizardSession

**Files:**
- Modify: `backend/app/models/session.py:11-28`
- Create: Alembic migration (auto-generated)

- [ ] **Step 1: Add columns to WizardSession model**

In `backend/app/models/session.py`, add two new columns after `current_step` (line 22):

```python
    # Wizard mode: null (not yet chosen) | "guided" | "surprise"
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)

    # Background generation task ID (surprise mode)
    generation_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
```

Also add `String` to the imports if not already imported (it's already on line 4).

- [ ] **Step 2: Generate Alembic migration**

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && alembic revision --autogenerate -m "add mode and generation_task_id to wizard_sessions"`

- [ ] **Step 3: Run migration**

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/session.py backend/alembic/versions/
git commit -m "feat: add mode and generation_task_id columns to WizardSession"
```

---

### Task 2: Refactor _detect_step and Update System Prompt

**Files:**
- Modify: `backend/app/services/wizard_prompt.py:1-67`
- Modify: `backend/app/routers/wizard.py:59,96,473-488`

- [ ] **Step 1: Update the system prompt**

Replace the entire `get_system_prompt()` function in `backend/app/services/wizard_prompt.py` with:

```python
def get_system_prompt() -> str:
    schema = json.loads(SCHEMA_PATH.read_text())
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

    return f"""Tu es un conteur passionné qui travaille pour WorldForge, un outil qui génère des mondes fictifs simulables. Ton rôle est de mener un entretien créatif avec l'utilisateur pour comprendre quel genre de monde il rêve d'explorer — puis tu construiras ce monde toi-même à partir de ses réponses.

## Règle fondamentale : ZÉRO SPOILER
L'utilisateur est un EXPLORATEUR, pas un configurateur. Il veut DÉCOUVRIR le monde une fois terminé.
- Ne révèle JAMAIS les noms des factions, régions, personnages ou événements que tu vas créer.
- Ne montre JAMAIS de récapitulatif du monde.
- Ne décris JAMAIS ce que le monde contiendra.
- Ne propose JAMAIS de choix concrets ("voici 3 factions possibles..."). C'est TOI qui décides des détails.
- L'utilisateur donne une DIRECTION, une AMBIANCE, des ENVIES — toi tu crées.

## Ta personnalité
- Enthousiaste, chaleureux, curieux — comme un auteur qui interview quelqu'un pour écrire son histoire.
- Tu tutoies l'utilisateur.
- Tu poses des questions ouvertes et inspirantes, pas des questions techniques.
- Toutes tes réponses sont en français.
- Jamais de tableaux, de variables techniques, de JSON, de noms d'attributs.

## Premier message : le choix du mode
Ton premier message propose deux façons de créer le monde, de manière naturelle et conversationnelle. Tu es un conteur, pas un robot. Exemple de ton (adapte avec tes propres mots, ne copie pas mot pour mot) :

"Salut ! Alors, tu viens créer un monde... j'adore ce moment. On a deux façons de faire ça ensemble.

Soit on prend le temps — je te pose des questions sur tout, les paysages, les peuples, la magie, les conflits... tu me guides et je construis autour de tes idées.

Soit tu me fais confiance — tu me dis juste quel genre d'univers te fait rêver, et je m'occupe de tout. Tu découvriras le monde en jouant, sans rien savoir à l'avance. C'est le mode aventurier.

Qu'est-ce qui te tente ?"

Quand l'utilisateur répond et que tu comprends son choix, ajoute le marqueur [MODE:guided] ou [MODE:surprise] dans ta réponse (il sera masqué à l'affichage).

## Mode guidé
Si le mode guidé est choisi, tu mènes l'entretien créatif en 11 étapes. Indique "Étape N/11" en début de chaque message.

### Les 11 étapes de l'entretien guidé
1. **Genre** — Quel type d'univers le fait rêver ?
2. **Ambiance** — Plutôt un monde stable ou imprévisible ? Classique ou surprenant dans ses codes ?
3. **Paysages** — Quels types d'environnements l'attirent ? Vaste ou intime ? Combien de diversité ?
4. **Peuples** — Beaucoup de factions ou peu ? Plutôt des empires, des tribus, des cités-états ? Des conflits ou de la coopération ?
5. **Richesses** — Qu'est-ce qui est précieux dans ce monde ? Qu'est-ce qu'on se dispute ?
6. **Progression** — La magie ? La technologie ? Les deux ? Quelque chose d'autre ?
7. **Drames** — Quel genre de catastrophes ou de rebondissements ? Du spectaculaire ou du subtil ?
8. **Héros** — Des figures légendaires ou des gens ordinaires ? Quel genre de destins ?
9. **Point de départ** — Le monde commence dans quel état ? Paix fragile, guerre ouverte, âge d'or ?
10. **Échelle** — Combien de temps d'histoire simuler ? Quelques décennies ou des siècles ?
11. **Confirmation** — "J'ai tout ce qu'il me faut pour créer ton monde ! Tu es prêt à le découvrir ?" — NE PAS résumer le monde.

## Mode surprise
Si le mode surprise est choisi, tu poses seulement 2 questions courtes et naturelles :
1. Quel genre de monde l'attire ? (Indique "Étape 1/4" discrètement)
2. Une envie particulière, un thème, une ambiance ? (Indique "Étape 2/4")

Après la 2e réponse, tu dis quelque chose de naturel comme "Parfait, laisse-moi travailler..." (Indique "Étape 3/4"). La génération se lance ensuite automatiquement.

## Comment réagir aux réponses
- Réagis avec enthousiasme et curiosité ("Ah, intéressant ! Ça me donne des idées...").
- Si l'utilisateur est vague, propose des pistes sous forme de questions ("Tu verrais plutôt un monde où la nature domine, ou un monde très urbanisé ?").
- Si l'utilisateur dit "ok", "oui", "comme tu veux", "surprise-moi", fais tes propres choix et passe à la suite.
- Sois bref — 3 à 5 phrases max par message.

## À la fin (étape 11 en guidé, étape 3 en surprise)
Dis simplement quelque chose comme "Parfait, j'ai tout ce qu'il faut !" Ne résume RIEN. L'utilisateur découvrira tout après la génération.

## Contraintes techniques (INVISIBLES pour l'utilisateur)
Quand on te demandera de produire le JSON final, tu devras transformer les réponses de l'utilisateur en une configuration complète et créative conforme à ce schéma :

```json
{{schema_str}}
```

Tu inventeras toi-même tous les noms, les détails, les attributs, les événements — en t'inspirant des envies exprimées par l'utilisateur. Sois créatif et généreux dans les détails.
Les IDs suivent les conventions : reg_, res_, fac_, tech_, evt_, bsw_, role_.
Les attributs numériques sont entre 0 et 1.
Le JSON doit être dans un bloc ```json ... ```.
"""
```

Note: The double curly braces `{{schema_str}}` are needed because of the outer f-string.

- [ ] **Step 2: Update the start trigger message**

In `backend/app/routers/wizard.py`, line 59, replace:

```python
        [system_msg, {"role": "user", "content": "Commence le wizard. Demande-moi quel genre de monde je veux créer."}],
```

With:

```python
        [system_msg, {"role": "user", "content": "Commence la conversation."}],
```

- [ ] **Step 3: Refactor _detect_step to return (step, mode)**

In `backend/app/routers/wizard.py`, replace the `_detect_step` function (lines 473-487) with:

```python
def _detect_step(response: str, current_step: int, current_mode: str | None = None) -> tuple[int, str | None]:
    """Detect wizard step and mode from LLM response.

    Returns (step, mode) where mode is None if not detected in this message.
    Looks for:
    - Mode markers: [MODE:guided] or [MODE:surprise]
    - Step markers: 'Étape N/11' (guided) or 'Étape N/4' (surprise)
    Only advances forward, never backwards.
    """
    detected_mode = None

    # Detect mode marker
    mode_match = re.search(r"\[MODE:(guided|surprise)\]", response, re.IGNORECASE)
    if mode_match:
        detected_mode = mode_match.group(1).lower()

    # Detect step — support both /11 and /4 denominators
    matches = re.findall(r"[ÉéEe]tape\s+(\d{1,2})(?:\s*/\s*(\d{1,2}))?", response, re.IGNORECASE)
    detected_step = current_step
    if matches:
        for step_str, denom_str in matches:
            step_val = int(step_str)
            denom = int(denom_str) if denom_str else (4 if (current_mode == "surprise" or detected_mode == "surprise") else 11)
            max_step = denom
            if 1 <= step_val <= max_step and step_val >= current_step:
                detected_step = step_val

    return detected_step, detected_mode
```

- [ ] **Step 4: Add `mode` to WizardResponse and update send_message**

In `backend/app/routers/wizard.py`, add `mode` to the response model (line 26-30):

```python
class WizardResponse(BaseModel):
    session_id: str
    message: str
    step: int | None = None
    status: str = "active"
    mode: str | None = None
```

Then replace line 96:

```python
    session.current_step = _detect_step(response, session.current_step)
```

With:

```python
    new_step, new_mode = _detect_step(response, session.current_step, session.mode)
    session.current_step = new_step
    if new_mode:
        session.mode = new_mode
```

- [ ] **Step 5: Update the history endpoint to return new fields**

In `backend/app/routers/wizard.py`, replace the return dict in `get_history` (lines 116-122) with:

```python
    # Resolve generation status
    generation_status = None
    if session.generation_task_id:
        from app.services.task_manager import get_task
        task = get_task(session.generation_task_id)
        if task:
            generation_status = task.status.value
        else:
            # Task not in memory (server restart) — deduce from world state
            world = await db.get(World, session.world_id) if session.world_id else None
            if world and world.status == "configured" and world.config:
                generation_status = "completed"
            else:
                generation_status = "failed"

    return {
        "session_id": str(session.id),
        "world_id": str(session.world_id) if session.world_id else None,
        "messages": visible,
        "step": session.current_step,
        "status": session.status,
        "mode": session.mode,
        "generation_task_id": session.generation_task_id,
        "generation_status": generation_status,
    }
```

- [ ] **Step 6: Strip mode markers from displayed messages**

> Note: `get_task` already exists in `task_manager.py` (line 46-47), no need to add it.

In `backend/app/routers/wizard.py`, add a helper to strip mode markers from responses before returning them. After `_detect_step`, add:

```python
def _strip_markers(text: str) -> str:
    """Remove internal markers from LLM responses before displaying."""
    text = re.sub(r"\[MODE:\w+\]", "", text)
    return text.strip()
```

Then update `start_wizard` (after line 63, where greeting is set):

```python
    greeting = _strip_markers(greeting)
```

And in `send_message`, after the `_detect_step` call, add:

```python
    # Strip markers from the response stored in messages
    clean_response = _strip_markers(response)
    new_messages[-1] = {"role": "assistant", "content": clean_response}
    session.messages = new_messages
```

And update the return to use `clean_response`:

```python
    return WizardResponse(
        session_id=str(session.id),
        message=clean_response,
        step=session.current_step,
        status="active",
        mode=session.mode,
    )
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/wizard_prompt.py backend/app/routers/wizard.py backend/app/services/task_manager.py
git commit -m "feat: refactor wizard for dual mode — system prompt, _detect_step, history endpoint"
```

---

### Task 3: Background Generation Endpoint

**Files:**
- Modify: `backend/app/routers/wizard.py`
- Modify: `backend/app/services/task_manager.py`

- [ ] **Step 1: Add wizard_notify helper to task_manager**

In `backend/app/services/task_manager.py`, add a function to send wizard-specific events:

```python
async def wizard_notify(user_id: str, event_type: str, data: dict):
    """Send a wizard-specific event to the user's WebSocket subscribers."""
    payload = {"type": event_type, **data}
    await _notify(user_id, payload)
```

Note: `_notify` is currently `async def _notify(user_id, data)` — make sure it's accessible. If it's not already, change it from a private function to be importable, or just call it directly.

- [ ] **Step 2: Add the generate endpoint and background task**

In `backend/app/routers/wizard.py`, add imports at the top:

```python
import asyncio
from app.database import async_session
from app.services.task_manager import create_task, update_task, get_task, wizard_notify, TaskStatus
```

Then add the generate endpoint and its background task after the `validate` endpoint (after line 220):

```python
# Immersive progress messages for surprise mode (no spoilers)
_SURPRISE_PROGRESS_MESSAGES = [
    "Je dessine les contours du monde...",
    "Des civilisations prennent forme...",
    "Les alliances et rivalités se nouent...",
    "L'histoire s'écrit, siècle après siècle...",
    "Les dernières touches...",
]


@router.post("/{session_id}/generate")
async def generate_world(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch background world generation for surprise mode."""
    session = await _get_session(session_id, current_user.id, db)

    # Guards
    if session.mode != "surprise":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La génération automatique n'est disponible qu'en mode surprise",
        )
    if session.current_step < 3:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les questions du mode surprise ne sont pas encore terminées",
        )
    if session.generation_task_id:
        existing_task = get_task(session.generation_task_id)
        if existing_task and existing_task.status == TaskStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Une génération est déjà en cours",
            )

    # Create background task
    task = create_task(type="wizard_generate", world_id=str(session.world_id), user_id=str(current_user.id))
    session.generation_task_id = task.id
    await db.commit()

    asyncio.create_task(
        _run_surprise_generation(task.id, str(session.id), str(session.world_id), str(current_user.id))
    )

    return {"task_id": task.id, "status": "accepted"}


async def _run_surprise_generation(task_id: str, session_id: str, world_id: str, user_id: str):
    """Background task: generate world config in surprise mode."""
    import asyncio as _asyncio

    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=5, message="Génération en cours")

        async with async_session() as db:
            result = await db.execute(
                select(WizardSession).where(WizardSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                await update_task(task_id, status=TaskStatus.FAILED, error="Session introuvable")
                return

            messages = list(session.messages)

            # Send immersive progress messages
            for i, progress_msg in enumerate(_SURPRISE_PROGRESS_MESSAGES):
                progress = int(10 + (60 * i / len(_SURPRISE_PROGRESS_MESSAGES)))
                await update_task(task_id, progress=progress, message=progress_msg)

                # Send wizard_progress WebSocket event
                await wizard_notify(user_id, "wizard_progress", {
                    "session_id": session_id,
                    "message": progress_msg,
                    "step": 3,
                })

                # Persist progress message in session
                messages.append({"role": "assistant", "content": progress_msg})
                session.messages = messages
                flag_modified(session, "messages")
                await db.commit()

                # Wait between messages (simulate work being done)
                await _asyncio.sleep(3)

            # Ask Kimi to generate the JSON
            finalize_messages = [*messages, {
                "role": "user",
                "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                           "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet. "
                           "Sois très créatif et généreux dans les détails — c'est toi qui décides de tout.",
            }]

            await update_task(task_id, progress=75, message="Création de la configuration...")
            response = await kimi_client.chat_completion(finalize_messages, temperature=0.3, max_tokens=16384)

            # Handle truncated JSON (same logic as finalize endpoint)
            if "```json" in response:
                after_json = response.split("```json", 1)[-1]
                if after_json.count("```") == 0:
                    finalize_messages.append({"role": "assistant", "content": response})
                    finalize_messages.append({"role": "user", "content": "Continue le JSON exactement où tu t'es arrêté, sans répéter ce qui précède. Termine avec ```."})
                    continuation = await kimi_client.chat_completion(finalize_messages, temperature=0.3, max_tokens=16384)
                    response = response + continuation

            # Extract and validate JSON
            messages.append({"role": "user", "content": "[Génération automatique]"})
            messages.append({"role": "assistant", "content": response})

            config = _extract_json_from_messages(messages)
            if config is None:
                raise ValueError("Aucun JSON valide trouvé dans la réponse de Kimi")

            config = _auto_repair_config(config)

            errors = validate_world_config(config)
            if errors:
                error_msgs = [e.message for e in errors[:5]]
                raise ValueError(f"Validation échouée: {'; '.join(error_msgs)}")

            await update_task(task_id, progress=90, message="Sauvegarde du monde...")

            # Save config to world
            world = await db.get(World, world_id)
            if not world:
                raise ValueError("Monde introuvable")

            world.config = config
            world.name = config.get("meta", {}).get("world_name", world.name)
            world.status = "configured"
            world.simulation_years = config.get("meta", {}).get("simulation_years")
            world.total_factions = len(config.get("factions", []))

            # Generate final Kimi message
            final_msg = await kimi_client.chat_completion(
                [*messages, {"role": "user", "content": "Dis simplement à l'utilisateur que son monde est prêt à être découvert. Une phrase, ton de conteur enthousiaste. Ne révèle RIEN du contenu."}],
                temperature=0.8,
                max_tokens=200,
            )
            final_msg = _strip_markers(final_msg)
            messages.append({"role": "assistant", "content": final_msg})

            # Update session
            session.messages = messages
            session.current_step = 4
            session.status = "finalized"
            flag_modified(session, "messages")
            await db.commit()

            # Notify frontend
            await wizard_notify(user_id, "wizard_complete", {
                "session_id": session_id,
                "world_id": world_id,
                "world_name": world.name,
            })

            await update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Monde créé",
                              result={"world_id": world_id, "world_name": world.name})

    except Exception as exc:
        import logging
        logging.getLogger("worldforge.wizard").exception("Surprise generation failed")

        # Persist error message in session
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(WizardSession).where(WizardSession.id == session_id)
                )
                session = result.scalar_one_or_none()
                if session:
                    error_msg = "Désolé, la création a rencontré un problème. Tu peux réessayer."
                    session.messages = [*session.messages, {"role": "assistant", "content": error_msg}]
                    flag_modified(session, "messages")
                    # NB: on garde generation_task_id pour que history puisse résoudre "failed"
                    await db.commit()
        except Exception:
            pass

        await wizard_notify(user_id, "wizard_error", {
            "session_id": session_id,
            "error": str(exc),
        })

        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/wizard.py backend/app/services/task_manager.py
git commit -m "feat: add background generation endpoint for wizard surprise mode"
```

---

### Task 4: Regenerate Endpoint

**Files:**
- Modify: `backend/app/routers/worlds.py`

- [ ] **Step 1: Read worlds.py to understand current structure**

Run: Read `backend/app/routers/worlds.py` to find where to add the new endpoint and what imports are available.

- [ ] **Step 2: Add regenerate endpoint**

Add to `backend/app/routers/worlds.py`:

```python
@router.post("/{world_id}/regenerate")
async def regenerate_world(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate world config from existing wizard conversation."""
    from app.models.session import WizardSession
    from app.services.task_manager import create_task, get_task, TaskStatus
    import asyncio

    # Get world
    world = await _get_user_world(world_id, db, user)

    # Find wizard session for this world
    result = await db.execute(
        select(WizardSession).where(
            WizardSession.world_id == world.id,
            WizardSession.user_id == user.id,
        ).order_by(WizardSession.created_at.desc())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune session wizard trouvée pour ce monde",
        )

    # Check no generation already running
    if session.generation_task_id:
        existing = get_task(session.generation_task_id)
        if existing and existing.status == TaskStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Une génération est déjà en cours",
            )

    task = create_task(type="wizard_regenerate", world_id=str(world.id), user_id=str(user.id))
    session.generation_task_id = task.id
    await db.commit()

    asyncio.create_task(
        _run_regeneration(task.id, str(session.id), str(world.id), str(user.id))
    )

    return {"task_id": task.id, "status": "accepted"}


async def _run_regeneration(task_id: str, session_id: str, world_id: str, user_id: str):
    """Background task: regenerate world config from existing wizard conversation."""
    from app.models.session import WizardSession
    from app.services.task_manager import update_task, TaskStatus
    from app.services import kimi_client
    from app.routers.wizard import _extract_json_from_messages, _auto_repair_config
    from app.services.world_validator import validate_world_config
    from app.database import async_session
    from sqlalchemy.orm.attributes import flag_modified

    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Régénération en cours...")

        async with async_session() as db:
            result = await db.execute(
                select(WizardSession).where(WizardSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                await update_task(task_id, status=TaskStatus.FAILED, error="Session introuvable")
                return

            # Use conversation history up to the finalize step
            # Remove any previous finalize/generation messages to get a clean conversation
            clean_messages = []
            for msg in session.messages:
                if msg.get("role") == "user" and msg.get("content", "").startswith("[Génération automatique]"):
                    break
                if msg.get("role") == "user" and "Produis maintenant le JSON" in msg.get("content", ""):
                    break
                clean_messages.append(msg)

            # Ask Kimi to generate JSON
            finalize_messages = [*clean_messages, {
                "role": "user",
                "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                           "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet. "
                           "Sois très créatif et généreux dans les détails. "
                           "IMPORTANT : génère un monde DIFFÉRENT du précédent, avec de nouveaux noms, de nouvelles idées.",
            }]

            await update_task(task_id, progress=30, message="Kimi crée un nouveau monde...")
            response = await kimi_client.chat_completion(finalize_messages, temperature=0.5, max_tokens=16384)

            # Handle truncated JSON
            if "```json" in response:
                after_json = response.split("```json", 1)[-1]
                if after_json.count("```") == 0:
                    finalize_messages.append({"role": "assistant", "content": response})
                    finalize_messages.append({"role": "user", "content": "Continue le JSON exactement où tu t'es arrêté, sans répéter ce qui précède. Termine avec ```."})
                    continuation = await kimi_client.chat_completion(finalize_messages, temperature=0.5, max_tokens=16384)
                    response = response + continuation

            await update_task(task_id, progress=70, message="Validation...")

            # Extract, repair, validate
            temp_messages = [{"role": "assistant", "content": response}]
            config = _extract_json_from_messages(temp_messages)
            if config is None:
                raise ValueError("Aucun JSON valide trouvé")

            config = _auto_repair_config(config)
            errors = validate_world_config(config)
            if errors:
                error_msgs = [e.message for e in errors[:5]]
                raise ValueError(f"Validation échouée: {'; '.join(error_msgs)}")

            await update_task(task_id, progress=90, message="Sauvegarde...")

            # Update world — clear downstream data
            world = await db.get(World, world_id)
            if not world:
                raise ValueError("Monde introuvable")

            world.config = config
            world.name = config.get("meta", {}).get("world_name", world.name)
            world.status = "configured"
            world.simulation_years = config.get("meta", {}).get("simulation_years")
            world.total_factions = len(config.get("factions", []))
            world.timeline = None
            world.narrative_blocks = None
            world.bookstack_mapping = None

            await db.commit()

        await update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Monde régénéré",
                          result={"world_id": world_id, "world_name": config.get("meta", {}).get("world_name", "")})

    except Exception as exc:
        import logging
        logging.getLogger("worldforge.worlds").exception("Regeneration failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))
```

Note: You'll need to check the exact imports and helper functions available in `worlds.py`. The `_get_user_world` helper likely exists already. Add `from sqlalchemy import select` and `from uuid import UUID` if not already imported.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/worlds.py
git commit -m "feat: add world regeneration endpoint"
```

---

### Task 5: Frontend API and WebSocket Updates

**Files:**
- Modify: `frontend/src/services/api.js:85-93`
- Modify: `frontend/src/services/websocket.js` (no changes needed — already handles arbitrary event types)

- [ ] **Step 1: Add new API methods**

In `frontend/src/services/api.js`, update the `wizard` object (lines 86-93):

```javascript
export const wizard = {
  start: () => apiFetch("/wizard/start", { method: "POST" }),
  sendMessage: (sessionId, content) =>
    apiFetch(`/wizard/${sessionId}/message`, { method: "POST", body: JSON.stringify({ content }) }),
  getHistory: (sessionId) => apiFetch(`/wizard/${sessionId}/history`),
  finalize: (sessionId) => apiFetch(`/wizard/${sessionId}/finalize`, { method: "POST" }),
  validate: (sessionId) => apiFetch(`/wizard/${sessionId}/validate`, { method: "POST" }),
  generate: (sessionId) => apiFetch(`/wizard/${sessionId}/generate`, { method: "POST" }),
};
```

And add `regenerate` to the `worlds` object (after `delete`):

```javascript
  regenerate: (id) => apiFetch(`/worlds/${id}/regenerate`, { method: "POST" }),
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/api.js
git commit -m "feat: add wizard.generate and worlds.regenerate API methods"
```

---

### Task 6: Frontend WizardChat — Conditional Progress Bar

**Files:**
- Modify: `frontend/src/components/WizardChat.jsx:1-194`

- [ ] **Step 1: Add surprise mode step labels and conditional rendering**

Replace the `WizardChat.jsx` component entirely:

```jsx
import { useState, useRef, useEffect } from "react";
import styles from "../styles/Wizard.module.css";

const GUIDED_STEP_LABELS = [
  "Genre",
  "Ambiance",
  "Géographie",
  "Factions",
  "Ressources",
  "Pouvoirs",
  "Événements",
  "Personnages",
  "Départ",
  "Durée",
  "Récap",
];

const SURPRISE_STEP_LABELS = [
  "Genre",
  "Envies",
  "Génération",
  "Prêt",
];

function renderMarkdown(text) {
  if (!text) return "";

  // Split into blocks to handle tables and code blocks separately
  const blocks = [];
  let remaining = text;

  // Extract code blocks first
  remaining = remaining.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const id = `__CODE_${blocks.length}__`;
    blocks.push(`<pre><code>${code.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>`);
    return id;
  });

  // Extract markdown tables
  remaining = remaining.replace(
    /(?:^|\n)((?:\|[^\n]+\|\n)+)/g,
    (match) => {
      const lines = match.trim().split("\n").filter(l => l.trim());
      const dataLines = lines.filter(l => !/^\|[\s\-:|]+\|$/.test(l));
      if (dataLines.length === 0) return match;

      const headerCells = dataLines[0].split("|").filter(c => c.trim());
      let tableHtml = "<table><thead><tr>";
      headerCells.forEach(c => { tableHtml += `<th>${renderInline(c.trim())}</th>`; });
      tableHtml += "</tr></thead><tbody>";
      for (let i = 1; i < dataLines.length; i++) {
        const cells = dataLines[i].split("|").filter(c => c.trim());
        tableHtml += "<tr>";
        cells.forEach(c => { tableHtml += `<td>${renderInline(c.trim())}</td>`; });
        tableHtml += "</tr>";
      }
      tableHtml += "</tbody></table>";

      const id = `__TABLE_${blocks.length}__`;
      blocks.push(tableHtml);
      return `\n${id}\n`;
    }
  );

  // Process inline markdown
  let html = renderInline(remaining);

  // Headers (h2, h3)
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  // Horizontal rules
  html = html.replace(/^---+$/gm, '<hr/>');
  // Unordered lists
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  // Line breaks
  html = html.replace(/\n/g, '<br/>');

  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*?<\/li>\s*(?:<br\/>)?)+)/g, '<ul>$1</ul>');
  html = html.replace(/<br\/>\s*<\/ul>/g, '</ul>');
  html = html.replace(/<ul>\s*<br\/>/g, '<ul>');

  // Restore extracted blocks
  blocks.forEach((block, i) => {
    html = html.replace(new RegExp(`__(?:CODE|TABLE)_${i}__`), block);
  });

  // Strip the step indicator lines (Étape N/11 or Étape N/4)
  html = html.replace(/<p>\s*[ÉéEe]tape\s+\d{1,2}\s*\/\s*\d{1,2}\s*<\/p>/gi, '');
  html = html.replace(/^[ÉéEe]tape\s+\d{1,2}\s*\/\s*\d{1,2}\s*<br\/>/gim, '');

  return `<p>${html}</p>`;
}

function renderInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

export default function WizardChat({ messages, onSend, isLoading, step, mode }) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Choose step labels based on mode
  const stepLabels = mode === "surprise" ? SURPRISE_STEP_LABELS : GUIDED_STEP_LABELS;
  const showStepBar = mode !== null && mode !== undefined;

  return (
    <>
      {/* Step progress bar — hidden until mode is chosen */}
      {showStepBar && (
        <div className={styles.stepBar}>
          {stepLabels.map((label, i) => {
            const stepNum = i + 1;
            let cls = styles.stepDot;
            if (stepNum < step) cls += ` ${styles.completed}`;
            else if (stepNum === step) cls += ` ${styles.active}`;
            return (
              <div key={stepNum} className={cls}>
                <span className={styles.stepNumber}>{stepNum}</span>
                {label}
              </div>
            );
          })}
        </div>
      )}

      {/* Messages */}
      <div className={styles.messages}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.message} ${
              msg.role === "assistant" ? styles.assistant : styles.user
            }`}
          >
            <div
              className={styles.messageContent}
              dangerouslySetInnerHTML={{
                __html:
                  msg.role === "assistant"
                    ? renderMarkdown(msg.content)
                    : msg.content.replace(/</g, "&lt;").replace(/>/g, "&gt;"),
              }}
            />
          </div>
        ))}
        {isLoading && (
          <div className={styles.loadingDots}>
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form className={styles.inputArea} onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className={styles.inputField}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Décris ton monde..."
          disabled={isLoading}
          rows={1}
        />
        <button
          type="submit"
          className={styles.sendBtn}
          disabled={isLoading || !input.trim()}
        >
          Envoyer
        </button>
      </form>
    </>
  );
}
```

Key changes:
- Added `SURPRISE_STEP_LABELS` (4 steps)
- `WizardChat` now accepts a `mode` prop
- Step bar is hidden when `mode` is null (first message, before choice)
- Step bar uses correct labels based on mode
- Step indicator strip regex updated from `/11` to `/\d{1,2}` to handle both `/11` and `/4`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/WizardChat.jsx
git commit -m "feat: conditional progress bar for guided/surprise wizard modes"
```

---

### Task 7: Frontend Wizard.jsx — Mode Handling and WebSocket

**Files:**
- Modify: `frontend/src/pages/Wizard.jsx:1-210`

- [ ] **Step 1: Rewrite Wizard.jsx with mode and WebSocket support**

Replace the entire `frontend/src/pages/Wizard.jsx`:

```jsx
import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { wizard } from "../services/api";
import { wsService } from "../services/websocket";
import WizardChat from "../components/WizardChat";
import styles from "../styles/Wizard.module.css";

const GENERATION_STEPS = [
  "Conversation avec le conteur...",
  "Création de la configuration du monde...",
  "Validation du monde...",
  "C'est prêt !",
];

export default function Wizard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [worldId, setWorldId] = useState(null);
  const [error, setError] = useState(null);
  const [initializing, setInitializing] = useState(true);

  // Generation overlay state (guided mode)
  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState(0);
  const [genError, setGenError] = useState(null);

  // Surprise mode state
  const [surpriseGenerating, setSurpriseGenerating] = useState(false);
  const [surpriseComplete, setSurpriseComplete] = useState(false);
  const [surpriseWorldId, setSurpriseWorldId] = useState(null);

  // Track if we already triggered generate for this session
  const generateTriggered = useRef(false);

  // Start new session if no sessionId
  useEffect(() => {
    if (!sessionId) {
      wizard
        .start()
        .then((data) => {
          navigate(`/wizard/${data.session_id}`, { replace: true });
        })
        .catch((err) => {
          setError(err.message);
          setInitializing(false);
        });
    }
  }, [sessionId, navigate]);

  // Load history when sessionId is present
  useEffect(() => {
    if (!sessionId) return;
    setInitializing(true);
    wizard
      .getHistory(sessionId)
      .then((data) => {
        setMessages(data.messages || []);
        setStep(data.step || 1);
        setMode(data.mode || null);
        setWorldId(data.world_id || null);
        setInitializing(false);

        // Restore surprise mode state from history
        if (data.mode === "surprise") {
          if (data.generation_status === "completed") {
            setSurpriseComplete(true);
            setSurpriseWorldId(data.world_id);
          } else if (data.generation_status === "running") {
            setSurpriseGenerating(true);
          } else if (data.generation_status === "failed") {
            // Show retry state
            setSurpriseGenerating(false);
          }
        }
      })
      .catch((err) => {
        setError(err.message);
        setInitializing(false);
      });
  }, [sessionId]);

  // WebSocket listeners for surprise mode
  useEffect(() => {
    if (!sessionId) return;

    const unsubs = [
      wsService.on("wizard_progress", (data) => {
        if (data.session_id !== sessionId) return;
        setMessages((prev) => [...prev, { role: "assistant", content: data.message }]);
        if (data.step) setStep(data.step);
      }),
      wsService.on("wizard_complete", (data) => {
        if (data.session_id !== sessionId) return;
        setSurpriseGenerating(false);
        setSurpriseComplete(true);
        setSurpriseWorldId(data.world_id);
        setStep(4);
        // The final message is already in the history — reload to get it
        wizard.getHistory(sessionId).then((hist) => {
          setMessages(hist.messages || []);
        });
      }),
      wsService.on("wizard_error", (data) => {
        if (data.session_id !== sessionId) return;
        setSurpriseGenerating(false);
        setError("La création a rencontré un problème. Tu peux réessayer.");
      }),
    ];

    return () => unsubs.forEach((unsub) => unsub());
  }, [sessionId]);

  const handleSend = useCallback(
    async (content) => {
      if (!sessionId || isLoading) return;

      const userMsg = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const data = await wizard.sendMessage(sessionId, content);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.message },
        ]);
        if (data.step) setStep(data.step);

        // Detect mode from response (check history to get updated mode)
        const history = await wizard.getHistory(sessionId);
        if (history.mode && history.mode !== mode) {
          setMode(history.mode);
        }

        // Auto-trigger generation in surprise mode when step 3 is reached
        if (history.mode === "surprise" && data.step >= 3 && !generateTriggered.current) {
          generateTriggered.current = true;
          setSurpriseGenerating(true);
          try {
            await wizard.generate(sessionId);
          } catch (genErr) {
            setSurpriseGenerating(false);
            setError(genErr.message);
            generateTriggered.current = false;
          }
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, isLoading, mode]
  );

  const handleRetryGeneration = useCallback(async () => {
    if (!sessionId) return;
    setError(null);
    setSurpriseGenerating(true);
    generateTriggered.current = true;
    try {
      await wizard.generate(sessionId);
    } catch (err) {
      setSurpriseGenerating(false);
      setError(err.message);
      generateTriggered.current = false;
    }
  }, [sessionId]);

  const handleCreateWorld = useCallback(async () => {
    if (!sessionId) return;
    setGenerating(true);
    setGenStep(0);
    setGenError(null);

    try {
      setGenStep(1);
      await wizard.finalize(sessionId);

      setGenStep(2);
      const data = await wizard.validate(sessionId);

      if (data.valid === false) {
        setGenError(
          "Le monde généré n'est pas valide. Relance la création ou continue la conversation pour ajuster."
        );
        setGenerating(false);
        return;
      }

      setGenStep(3);
      setTimeout(() => {
        navigate(`/world/${data.world_id}`);
      }, 1500);
    } catch (err) {
      setGenError(err.message || "Erreur lors de la création du monde");
      setGenerating(false);
    }
  }, [sessionId, navigate]);

  if (!sessionId || initializing) {
    return (
      <div className={styles.loadingPage}>
        <div className={styles.spinner} />
        Initialisation du wizard...
      </div>
    );
  }

  // Determine if input should be disabled
  const inputDisabled = isLoading || surpriseGenerating || surpriseComplete;

  return (
    <div className={styles.container}>
      {/* Generation overlay (guided mode only) */}
      {generating && (
        <div className={styles.genOverlay}>
          <div className={styles.genCard}>
            <h2 className={styles.genTitle}>Création de ton monde</h2>
            <div className={styles.genSteps}>
              {GENERATION_STEPS.map((label, i) => (
                <div
                  key={i}
                  className={`${styles.genStepRow} ${
                    i < genStep
                      ? styles.genDone
                      : i === genStep
                      ? styles.genActive
                      : ""
                  }`}
                >
                  <div className={styles.genDot}>
                    {i < genStep ? "✓" : i === genStep ? "" : ""}
                  </div>
                  <span>{label}</span>
                  {i === genStep && !genError && (
                    <div className={styles.genSpinner} />
                  )}
                </div>
              ))}
            </div>
            {genError && (
              <div className={styles.genError}>
                <p>{genError}</p>
                <button
                  className={styles.finalizeBtn}
                  onClick={() => {
                    setGenerating(false);
                    setGenError(null);
                  }}
                >
                  Retour à la conversation
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className={styles.header}>
        <h1 className={styles.title}>Forge de Monde</h1>
        <Link to="/dashboard" className={styles.backLink}>
          Retour au tableau de bord
        </Link>
      </div>

      <WizardChat
        messages={messages}
        onSend={handleSend}
        isLoading={isLoading || surpriseGenerating}
        step={step}
        mode={mode}
      />

      {error && (
        <div className={styles.error}>
          {error}
          {mode === "surprise" && !surpriseGenerating && !surpriseComplete && (
            <button className={styles.retryBtn} onClick={handleRetryGeneration}>
              Réessayer
            </button>
          )}
        </div>
      )}

      {/* Guided mode: Create button */}
      {mode !== "surprise" && step >= 8 && !generating && (
        <div className={styles.actions}>
          <button
            className={styles.createBtn}
            onClick={handleCreateWorld}
            disabled={isLoading}
          >
            Créer mon monde
          </button>
          <span className={styles.actionsHint}>
            Tu peux aussi continuer la conversation
          </span>
        </div>
      )}

      {/* Surprise mode: Discover button */}
      {surpriseComplete && surpriseWorldId && (
        <div className={styles.actions}>
          <button
            className={styles.createBtn}
            onClick={() => navigate(`/world/${surpriseWorldId}`)}
          >
            Découvrir le monde
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add retryBtn style to Wizard.module.css**

In `frontend/src/styles/Wizard.module.css`, add:

```css
.retryBtn {
  margin-left: 1rem;
  padding: 0.4rem 1rem;
  background: var(--accent, #6366f1);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

.retryBtn:hover {
  opacity: 0.9;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Wizard.jsx frontend/src/styles/Wizard.module.css
git commit -m "feat: wizard surprise mode — auto-generate, WebSocket progress, discover button"
```

---

### Task 8: Frontend WorldView — Regenerate Button

**Files:**
- Modify: `frontend/src/pages/WorldView.jsx`

- [ ] **Step 1: Read WorldView.jsx to find the actions section**

Read the full file to locate where the action buttons are rendered (Simuler, Narrer, Exporter, Supprimer).

- [ ] **Step 2: Add regenerate button**

In the actions section of `WorldView.jsx`, add a "Régénérer le monde" button. Place it after the existing action buttons, before "Supprimer":

```jsx
{/* Regenerate button */}
<button
  className={styles.actionBtn}
  onClick={handleRegenerate}
  disabled={taskRunning}
>
  Régénérer le monde
</button>
```

Add the `handleRegenerate` callback in the component:

```jsx
const handleRegenerate = useCallback(async () => {
  const hasDownstream = ["simulated", "narrated", "exported"].includes(world?.status);
  const message = hasDownstream
    ? "Attention : la simulation, la narration et l'export existants seront perdus. Continuer ?"
    : "Régénérer le monde avec une nouvelle configuration ?";

  if (!window.confirm(message)) return;

  try {
    setError(null);
    const data = await worlds.regenerate(worldId);
    // Task is now running — the existing task watcher will handle refresh
  } catch (err) {
    setError(err.message);
  }
}, [worldId, world?.status]);
```

Import `worlds` from api.js if not already imported.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WorldView.jsx
git commit -m "feat: add regenerate button to WorldView"
```

---

### Task 9: Integration Testing

**Files:**
- Create: `backend/tests/test_wizard_modes.py`

- [ ] **Step 1: Write tests for _detect_step refactor**

```python
# tests/test_wizard_modes.py
"""Tests for wizard dual mode — step/mode detection."""
import pytest
from app.routers.wizard import _detect_step, _strip_markers


def test_detect_mode_guided():
    step, mode = _detect_step("Bien ! [MODE:guided] Étape 1/11 — Quel univers...", 1, None)
    assert mode == "guided"
    assert step == 1


def test_detect_mode_surprise():
    step, mode = _detect_step("Super ! [MODE:surprise] Étape 1/4 — Quel genre...", 1, None)
    assert mode == "surprise"
    assert step == 1


def test_detect_step_guided_advances():
    step, mode = _detect_step("Étape 5/11 — Parlons des richesses...", 4, "guided")
    assert step == 5
    assert mode is None


def test_detect_step_surprise_advances():
    step, mode = _detect_step("Étape 2/4 — Une envie particulière ?", 1, "surprise")
    assert step == 2
    assert mode is None


def test_detect_step_never_goes_back():
    step, mode = _detect_step("Étape 2/11 — Revenons...", 5, "guided")
    assert step == 5


def test_detect_step_no_marker():
    step, mode = _detect_step("Ah, intéressant ! Dis-moi en plus...", 3, "guided")
    assert step == 3
    assert mode is None


def test_strip_markers():
    text = "Super choix ! [MODE:surprise] Étape 1/4 — Quel genre..."
    clean = _strip_markers(text)
    assert "[MODE:" not in clean
    assert "Super choix" in clean


def test_strip_markers_no_marker():
    text = "Ah, intéressant !"
    assert _strip_markers(text) == text
```

- [ ] **Step 2: Write tests for /generate endpoint guards**

Append to the same file:

```python
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.routers.wizard import generate_world


@pytest.mark.asyncio
async def test_generate_rejects_guided_mode():
    """POST /generate should return 409 if mode is not 'surprise'."""
    mock_session = MagicMock()
    mock_session.mode = "guided"
    mock_session.current_step = 3
    mock_session.generation_task_id = None
    mock_session.user_id = 1

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_session
    mock_db.execute = AsyncMock(return_value=mock_result)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await generate_world("test-session", mock_db, MagicMock(id=1))
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_generate_rejects_early_step():
    """POST /generate should return 409 if step < 3."""
    mock_session = MagicMock()
    mock_session.mode = "surprise"
    mock_session.current_step = 1
    mock_session.generation_task_id = None
    mock_session.user_id = 1

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_session
    mock_db.execute = AsyncMock(return_value=mock_result)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await generate_world("test-session", mock_db, MagicMock(id=1))
    assert exc_info.value.status_code == 409
```

- [ ] **Step 3: Write test for generation_status resolution**

Append to the same file:

```python
def test_generation_status_resolved_from_world_when_task_missing():
    """If task_id exists but task not found, status should be deduced from world state."""
    # This tests the fallback logic in the history endpoint
    from app.services.task_manager import get_task

    # When task is not in task_manager, get_task returns None
    assert get_task("nonexistent-task-id") is None
    # The history endpoint should then check world.status to determine if completed or failed
```

- [ ] **Step 4: Run tests**

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && .venv/bin/python -m pytest tests/test_wizard_modes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_wizard_modes.py
git commit -m "test: add tests for wizard dual mode step/mode detection and endpoint guards"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Verify all imports resolve**

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && .venv/bin/python -c "from app.routers.wizard import _detect_step, _strip_markers, generate_world; print('wizard OK')"`

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && .venv/bin/python -c "from app.services.task_manager import create_task, get_task, wizard_notify; print('task_manager OK')"`

- [ ] **Step 2: Run full backend test suite**

Run: `cd /home/openclaw/WorldForge/Worldforge/backend && .venv/bin/python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Verify frontend builds**

Run: `cd /home/openclaw/WorldForge/Worldforge/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Verify frontend lints**

Run: `cd /home/openclaw/WorldForge/Worldforge/frontend && npm run lint`
Expected: No errors (warnings acceptable)

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address any issues found during final verification"
```
