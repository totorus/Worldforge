"""Kimi K2.5 API client for wizard conversations and coherence checks."""

import httpx

from app.config import settings

KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"
KIMI_MODEL = "kimi-k2-0711"


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion request to Kimi K2.5. Returns assistant message content."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            KIMI_API_URL,
            headers={
                "Authorization": f"Bearer {settings.kimi_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """Stream a chat completion from Kimi K2.5. Yields content chunks."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            KIMI_API_URL,
            headers={
                "Authorization": f"Bearer {settings.kimi_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
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
