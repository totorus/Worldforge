"""LLM routing — dispatches tasks to the appropriate LLM provider and model."""

import asyncio
import logging

from app.services import kimi_client, openrouter_client

logger = logging.getLogger("worldforge.llm_router")

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds

# Task → LLM mapping (from specs section 6.3)
TASK_ROUTING = {
    # Kimi K2.5
    "wizard": "kimi",
    "era_splitting": "kimi",
    "coherence_check": "kimi",

    # Mistral Small Creative (OpenRouter)
    "faction_sheet": "mistral_creative",
    "region_sheet": "mistral_creative",
    "event_narrative": "mistral_creative",
    "character_biography": "mistral_creative",
    "legend": "mistral_creative",

    # Mistral Small 4 (OpenRouter)
    "naming": "mistral_small",
    "summary": "mistral_small",
    "tech_description": "mistral_small",

    # Entity extraction (Kimi K2.5)
    "entity_detection": "kimi",

    # Entity sheet generation (Mistral Creative)
    "entity_sheet": "mistral_creative",
    "cosmogony": "mistral_creative",
    "race_sheet": "mistral_creative",
    "fauna_sheet": "mistral_creative",
    "flora_sheet": "mistral_creative",
    "bestiary_sheet": "mistral_creative",
    "location_sheet": "mistral_creative",
    "resource_sheet": "mistral_creative",
    "organization_sheet": "mistral_creative",
    "artifact_sheet": "mistral_creative",

    # Coherence fix (Mistral Creative — rewrites narrative blocks)
    "coherence_fix": "mistral_creative",
}


async def _call_provider(provider: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    """Single call to the appropriate provider (no retry)."""
    if provider == "kimi":
        return await kimi_client.chat_completion(messages, temperature, max_tokens)
    elif provider == "mistral_creative":
        return await openrouter_client.chat_completion(messages, "mistral_small_creative", temperature, max_tokens)
    else:
        return await openrouter_client.chat_completion(messages, "mistral_small_4", temperature, max_tokens)


async def complete(
    task: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Route a task to the appropriate LLM with retry and exponential backoff."""
    provider = TASK_ROUTING.get(task, "mistral_small")
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await _call_provider(provider, messages, temperature, max_tokens)
            if attempt > 1:
                logger.info("[%s] Succeeded on attempt %d/%d", task, attempt, MAX_RETRIES)
            return result
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "[%s] Attempt %d/%d failed (%s: %s), retrying in %.1fs",
                    task, attempt, MAX_RETRIES, type(e).__name__, str(e)[:200], delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "[%s] All %d attempts failed. Last error: %s: %s",
                    task, MAX_RETRIES, type(e).__name__, str(e)[:500],
                )

    raise last_error


async def stream(
    task: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """Route a task to the appropriate LLM and stream the response."""
    provider = TASK_ROUTING.get(task, "mistral_small")

    if provider == "kimi":
        async for chunk in kimi_client.chat_completion_stream(messages, temperature, max_tokens):
            yield chunk
    elif provider == "mistral_creative":
        async for chunk in openrouter_client.chat_completion_stream(messages, "mistral_small_creative", temperature, max_tokens):
            yield chunk
    else:
        async for chunk in openrouter_client.chat_completion_stream(messages, "mistral_small_4", temperature, max_tokens):
            yield chunk
