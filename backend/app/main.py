from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, wizard, simulate, narrate, export, worlds, ws, tasks

app = FastAPI(title="WorldForge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(wizard.router, prefix="/api/wizard", tags=["wizard"])
app.include_router(simulate.router, prefix="/api/simulate", tags=["simulate"])
app.include_router(narrate.router, prefix="/api/narrate", tags=["narrate"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(worlds.router, prefix="/api/worlds", tags=["worlds"])
app.include_router(ws.router, tags=["websocket"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_checks():
    missing = []
    if not settings.kimi_api_key or settings.kimi_api_key.startswith("sk-kimi-xxx"):
        missing.append("KIMI_API_KEY")
    if not settings.openrouter_api_key or settings.openrouter_api_key.startswith("sk-or-v1-xxx"):
        missing.append("OPENROUTER_API_KEY")
    if missing:
        raise RuntimeError(f"Missing required API keys: {', '.join(missing)}")

    if not settings.bookstack_token_id or not settings.bookstack_token_secret:
        import logging
        logging.getLogger("worldforge").warning(
            "Bookstack API tokens not configured — export will be unavailable"
        )
