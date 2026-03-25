"""LLM routing — dispatches tasks to the appropriate LLM provider and model."""

from app.services import kimi_client, openrouter_client

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


async def complete(
    task: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Route a task to the appropriate LLM and return the response."""
    provider = TASK_ROUTING.get(task, "mistral_small")

    if provider == "kimi":
        return await kimi_client.chat_completion(messages, temperature, max_tokens)
    elif provider == "mistral_creative":
        return await openrouter_client.chat_completion(messages, "mistral_small_creative", temperature, max_tokens)
    else:
        return await openrouter_client.chat_completion(messages, "mistral_small_4", temperature, max_tokens)


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
