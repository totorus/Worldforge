"""Async HTTP client for the Bookstack REST API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("worldforge.bookstack")

# Retry configuration for 429 (rate-limit) responses
_MAX_RETRIES = 5
_INITIAL_BACKOFF = 1.0  # seconds


class BookstackClient:
    """Thin async wrapper around the Bookstack REST API.

    All heavy methods return the parsed JSON body of the created/updated
    entity so the caller can retrieve the ``id`` field.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.bookstack_url).rstrip("/")
        self.token_id = token_id or settings.bookstack_token_id
        self.token_secret = token_secret or settings.bookstack_token_secret

        if not self.token_id or not self.token_secret:
            raise RuntimeError(
                "Bookstack API tokens not configured "
                "(BOOKSTACK_TOKEN_ID / BOOKSTACK_TOKEN_SECRET)"
            )

        self._headers = {
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with automatic retry on 429."""
        url = f"{self.base_url}/api{path}"
        backoff = _INITIAL_BACKOFF

        for attempt in range(1, _MAX_RETRIES + 1):
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method, url, headers=self._headers, json=json
                )

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", backoff))
                logger.warning(
                    "Bookstack rate-limited (429), retry %d/%d in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    retry_after,
                )
                await asyncio.sleep(retry_after)
                backoff *= 2
                continue

            resp.raise_for_status()
            return resp.json()

        raise httpx.HTTPStatusError(
            "Rate-limited after max retries",
            request=resp.request,
            response=resp,
        )

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=data)

    async def _put(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", path, json=data)

    async def _get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def _delete(self, path: str) -> None:
        """DELETE request (no JSON body expected back)."""
        url = f"{self.base_url}/api{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(url, headers=self._headers)
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Listing / search helpers
    # ------------------------------------------------------------------

    async def list_shelves(self) -> list[dict[str, Any]]:
        """GET /api/shelves — return all shelves."""
        result = await self._get("/shelves")
        return result.get("data", [])

    async def find_shelf_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a shelf by exact name, or return None."""
        shelves = await self.list_shelves()
        for s in shelves:
            if s.get("name") == name:
                return s
        return None

    # ------------------------------------------------------------------
    # Shelves
    # ------------------------------------------------------------------

    async def create_shelf(
        self, name: str, description: str = "", books: list[int] | None = None
    ) -> dict[str, Any]:
        """POST /api/shelves"""
        payload: dict[str, Any] = {"name": name, "description": description}
        if books:
            payload["books"] = books
        return await self._post("/shelves", payload)

    async def attach_book_to_shelf(
        self, shelf_id: int, book_ids: list[int]
    ) -> dict[str, Any]:
        """PUT /api/shelves/{id} — update the books attached to a shelf."""
        return await self._put(f"/shelves/{shelf_id}", {"books": book_ids})

    # ------------------------------------------------------------------
    # Books
    # ------------------------------------------------------------------

    async def create_book(
        self, name: str, description: str = ""
    ) -> dict[str, Any]:
        """POST /api/books"""
        return await self._post("/books", {"name": name, "description": description})

    # ------------------------------------------------------------------
    # Chapters
    # ------------------------------------------------------------------

    async def create_chapter(
        self, book_id: int, name: str, description: str = ""
    ) -> dict[str, Any]:
        """POST /api/chapters"""
        return await self._post(
            "/chapters",
            {"book_id": book_id, "name": name, "description": description},
        )

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    async def create_page(
        self,
        *,
        book_id: int | None = None,
        chapter_id: int | None = None,
        name: str,
        html: str = "",
    ) -> dict[str, Any]:
        """POST /api/pages — create a page inside a book or a chapter."""
        payload: dict[str, Any] = {"name": name, "html": html}
        if chapter_id is not None:
            payload["chapter_id"] = chapter_id
        elif book_id is not None:
            payload["book_id"] = book_id
        else:
            raise ValueError("Either book_id or chapter_id is required")
        return await self._post("/pages", payload)

    async def update_page(
        self, page_id: int, *, name: str | None = None, html: str | None = None
    ) -> dict[str, Any]:
        """PUT /api/pages/{id}"""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if html is not None:
            payload["html"] = html
        return await self._put(f"/pages/{page_id}", payload)
