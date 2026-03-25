"""OpenRouter API client for Mistral Small Creative and Mistral Small 4."""

import httpx
import logging

from app.config import settings
from app.services.openrouter_models import MODELS

logger = logging.getLogger("worldforge.openrouter")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


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
            },
        )
        if response.status_code != 200:
            print(f"[OpenRouter] ERROR {response.status_code} for {model_id}: {response.text[:500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content") or ""
        finish = data["choices"][0].get("finish_reason", "?")
        print(f"[OpenRouter] model={model_id} status={response.status_code} content_len={len(content)} finish={finish}", flush=True)
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
