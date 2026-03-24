# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

WorldForge — webapp de génération procédurale de mondes fictifs multi-genre. Quatre phases : wizard conversationnel (LLM) → simulateur procédural (Python pur) → enrichissement narratif (LLM) → export wiki Bookstack.

Specs complètes : `/home/openclaw/WorldForge/SPECS_WORLDFORGE.md`
Exemple de config monde : `/home/openclaw/WorldForge/world_config_example.json`

## Stack

- **Frontend** : React (port 5214)
- **Backend** : Python FastAPI (port 8000)
- **Base de données** : PostgreSQL 16
- **Cache/sessions** : Redis 7
- **Wiki** : Bookstack (intégré Docker Compose, port 6875)
- **LLMs** (tout via OpenRouter, pas d'Ollama) :
  - Kimi K2.5 — wizard, découpage en ères, validation cohérence
  - Mistral Small Creative — narration, fiches, biographies, légendes
  - Mistral Small 4 — tâches légères (nommage, résumés)

## Commands

```bash
# Dev
docker compose up              # Stack complète
docker compose up --build      # Rebuild après modifs

# Backend seul
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend seul
cd frontend && npm run dev -- --port 5214

# Tests
cd backend && pytest
cd backend && pytest tests/test_simulator.py -k "test_name"  # Test unique

# Lint
cd backend && ruff check .
cd frontend && npm run lint

# DB migrations
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

## Architecture

```
worldforge/
├── docker-compose.yml
├── .env                    # Secrets (gitignored)
├── frontend/               # React app
│   └── src/
│       ├── pages/          # Login, Dashboard, Wizard, WorldView, Timeline, Narrative, ConfigEditor
│       ├── components/     # WizardChat, WorldCard, TimelineViewer, NarrativeReader, WorldGraph
│       └── services/       # api.js, websocket.js
├── backend/
│   └── app/
│       ├── main.py         # FastAPI app + routes
│       ├── routers/        # auth, wizard, simulate, narrate, export, worlds
│       ├── services/       # llm_router, kimi_client, openrouter_client, bookstack_client
│       ├── simulator/      # Moteur procédural (engine, events, factions, tech, characters, relations, preconditions, conflict)
│       ├── narrator/       # Pipeline LLM (naming, eras, factions, regions, events, characters, legends, coherence)
│       └── exporter/       # Export Bookstack
│   └── schemas/
│       └── world_config.json  # JSON Schema de validation
```

Le simulateur est **genre-agnostique** — il manipule des abstractions (factions, régions, ressources, événements). Le genre est porté par la config JSON, pas par le code. Les LLM n'interviennent jamais dans la boucle de simulation.

## Réseau & Déploiement

- Serveur : `172.16.16.99` sur `172.16.16.0/24`
- `https://worldforge.ssantoro.fr` → frontend (port 5214) + `/api` → backend (port 8000)
- `https://worlds.ssantoro.fr` → Bookstack (port 6875)
- SSL via Nginx Proxy Manager

## Sécurité

- Clés API dans `/home/openclaw/WorldForge/api.txt` — **ne jamais afficher, ne jamais mettre dans les specs ou le code**
- `.env` et `api.txt` dans `.gitignore`
- Le backend valide la présence des variables d'environnement au démarrage (fail fast)
- Auth utilisateur par JWT (bcrypt pour les mots de passe)

## Conventions

- Tout le contenu généré est en **français**
- Communication frontend ↔ backend : REST + WebSocket (tâches longues)
- Tâches longues (simulation, narration, export) : asynchrones, progression via WebSocket
