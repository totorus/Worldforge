"""Kimi K2.5 API client for wizard conversations and coherence checks."""

import httpx

from app.config import settings

KIMI_BASE_URL = "https://api.kimi.com/coding/v1/"
KIMI_MODEL = "k2p5"


def _build_anthropic_body(messages: list[dict], temperature: float, max_tokens: int) -> tuple[dict, list[dict]]:
    """Convert OpenAI-style messages to Anthropic messages API format.
    Returns (system_text, messages_list)."""
    system = ""
    converted = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            converted.append({"role": msg["role"], "content": msg["content"]})
    return system, converted


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion request to Kimi K2.5 (Anthropic messages API). Returns assistant message content."""
    system, msgs = _build_anthropic_body(messages, temperature, max_tokens)
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{KIMI_BASE_URL}messages",
            headers={
                "x-api-key": settings.kimi_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
                "system": system,
                "messages": msgs,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "thinking": {"type": "disabled"},
            },
        )
        response.raise_for_status()
        data = response.json()
        # Anthropic format: {"content": [{"type": "text", "text": "..."}]}
        for block in data["content"]:
            if block["type"] == "text":
                return block["text"]
        return ""


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """Stream a chat completion from Kimi K2.5. Yields content chunks."""
    system, msgs = _build_anthropic_body(messages, temperature, max_tokens)
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{KIMI_BASE_URL}messages",
            headers={
                "x-api-key": settings.kimi_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
                "system": system,
                "messages": msgs,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                "thinking": {"type": "disabled"},
            },
        ) as response:
            response.raise_for_status()
            import json
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("type") == "content_block_delta":
                    text = chunk.get("delta", {}).get("text", "")
                    if text:
                        yield text
