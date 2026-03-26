"""OpenRouter API client for Mistral Small Creative and Mistral Small 4."""

import json as _json
import httpx
import logging

from app.config import settings
from app.services.openrouter_models import MODELS

logger = logging.getLogger("worldforge.openrouter")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Hard cap on response length — Mistral Small Creative sometimes ignores max_tokens
# and returns 30k-130k char responses. Truncate to a reasonable size.
MAX_RESPONSE_CHARS = 12000


def _smart_truncate(content: str, limit: int) -> str:
    """Truncate oversized LLM response while trying to preserve valid JSON.

    Strategy: strip markdown fences, find the last complete JSON array item
    or object within the limit, then close open brackets/braces.
    """
    import re

    # Strip markdown code fences before processing
    stripped = content.strip()
    stripped = re.sub(r'^```(?:json)?\s*\n?', '', stripped)
    stripped = re.sub(r'\n?```\s*$', '', stripped)

    truncated = stripped[:limit]

    # Try to find the last complete JSON object boundary ("},") within the limit
    last_obj_end = truncated.rfind("},")
    if last_obj_end > limit * 0.4:
        truncated = truncated[:last_obj_end + 1]

    # Track open brackets/braces properly (respecting strings)
    in_string = False
    escape = False
    stack = []
    for ch in truncated:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append('}' if ch == '{' else ']')
        elif ch in '}]':
            if stack and stack[-1] == ch:
                stack.pop()

    # Close any open string
    if in_string:
        truncated += '"'

    # Remove trailing incomplete key-value pair
    truncated = re.sub(r',\s*"[^"]*"?\s*:?\s*"?[^"]*$', '', truncated)
    truncated = re.sub(r',\s*$', '', truncated)

    # Close open brackets/braces in reverse order
    truncated += ''.join(reversed(stack))

    # Verify result is valid JSON
    try:
        _json.loads(truncated)
        return truncated
    except _json.JSONDecodeError:
        # Fallback: return stripped (without fences) but raw cut
        return stripped[:limit]


async def chat_completion(
    messages: list[dict],
    model_key: str = "mistral_small_creative",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion request to OpenRouter. Returns assistant message content."""
    model_id = MODELS[model_key]

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://worldforge.ssantoro.fr",
                "X-Title": "WorldForge",
            },
            json={
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "max_completion_tokens": max_tokens,
            },
        )
        if response.status_code != 200:
            print(f"[OpenRouter] ERROR {response.status_code} for {model_id}: {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content") or ""
        finish = data["choices"][0].get("finish_reason", "?")
        original_len = len(content)
        if original_len > MAX_RESPONSE_CHARS:
            logger.warning(
                "[OpenRouter] Response too large (%d chars), truncating to %d for model=%s",
                original_len, MAX_RESPONSE_CHARS, model_id,
            )
            content = _smart_truncate(content, MAX_RESPONSE_CHARS)
        print(f"[OpenRouter] model={model_id} status={response.status_code} content_len={original_len} finish={finish}", flush=True)
        if not content:
            print(f"[OpenRouter] EMPTY CONTENT! Full response: {response.text[:1000]}", flush=True)
        return content


async def chat_completion_stream(
    messages: list[dict],
    model_key: str = "mistral_small_creative",
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """Stream a chat completion from OpenRouter. Yields content chunks."""
    model_id = MODELS[model_key]

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://worldforge.ssantoro.fr",
                "X-Title": "WorldForge",
            },
            json={
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    import json
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
