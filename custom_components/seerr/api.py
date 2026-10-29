"""Minimal asynchronous client for the Seerr (Overseerr/Jellyseerr) API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any
from urllib.parse import quote

import aiohttp
from yarl import URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class SeerrError(Exception):
    """Base error for Seerr API failures."""


class SeerrConnectionError(SeerrError):
    """The server could not be reached or timed out."""


class SeerrAuthError(SeerrError):
    """The API key was rejected."""


class SeerrResponseError(SeerrError):
    """The server answered with an error or an unexpected payload."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.status = status


class MediaStatus(IntEnum):
    """Seerr's media status (mediaInfo.status)."""

    UNKNOWN = 1
    PENDING = 2
    PROCESSING = 3
    PARTIALLY_AVAILABLE = 4
    AVAILABLE = 5
    BLOCKLISTED = 6
    DELETED = 7


@dataclass(frozen=True, slots=True)
class MediaResult:
    """A movie or TV show from a Seerr search."""

    tmdb_id: int
    media_type: str
    title: str
    year: int | None
    overview: str
    status: MediaStatus
    vote_count: int = 0

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> MediaResult:
        """Build a result from a search item."""
        date = item.get("releaseDate") or item.get("firstAirDate") or ""
        raw_status = (item.get("mediaInfo") or {}).get("status", MediaStatus.UNKNOWN)
        try:
            status = MediaStatus(raw_status)
        except ValueError:
            status = MediaStatus.UNKNOWN
        return cls(
            tmdb_id=item["id"],
            media_type=item["mediaType"],
            title=item.get("title") or item.get("name") or "",
            year=int(date[:4]) if date[:4].isdigit() else None,
            overview=item.get("overview") or "",
            status=status,
            vote_count=item.get("voteCount") or 0,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict for action and tool responses."""
        return {
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type,
            "title": self.title,
            "year": self.year,
            "status": self.status.name.lower(),
            "overview": self.overview,
        }


class SeerrClient:
    """Talk to one Seerr server."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"X-Api-Key": api_key, "Accept": "application/json"}

    async def _request(
        self, method: str, path: str, *, query: str = "", json: Any = None
    ) -> Any:
        # Seerr rejects queries that are not percent-encoded like
        # encodeURIComponent (a '+' for a space or a bare '!' gives a 400).
        url = URL(f"{self._url}/api/v1{path}{query}", encoded=True)
        try:
            async with self._session.request(
                method, url, headers=self._headers, json=json, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise SeerrAuthError(f"API key rejected ({resp.status})")
                if resp.status >= 400:
                    text = await resp.text()
                    raise SeerrResponseError(
                        f"HTTP {resp.status}: {text[:200]}", resp.status
                    )
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SeerrConnectionError(str(err) or type(err).__name__) from err
        except ValueError as err:
            raise SeerrResponseError(f"Invalid JSON: {err}") from err

    async def async_get_user(self) -> dict[str, Any]:
        """Return the user the API key belongs to (validates the key)."""
        data = await self._request("GET", "/auth/me")
        if not isinstance(data, dict) or "id" not in data:
            raise SeerrResponseError("Not a Seerr server")
        return data

    async def async_search(self, query: str) -> list[MediaResult]:
        """Search movies and TV shows, in TMDB relevance order."""
        data = await self._request(
            "GET", "/search", query=f"?query={quote(query, safe='')}&page=1"
        )
        try:
            return [
                MediaResult.from_api(item)
                for item in data["results"]
                if item.get("mediaType") in ("movie", "tv")
            ]
        except (KeyError, TypeError) as err:
            raise SeerrResponseError(f"Unexpected search response: {err}") from err

    async def async_request(
        self, media_type: str, tmdb_id: int, *, is_4k: bool = False
    ) -> dict[str, Any]:
        """Request a movie, or every season of a TV show."""
        body: dict[str, Any] = {
            "mediaType": media_type,
            "mediaId": tmdb_id,
            "is4k": is_4k,
        }
        if media_type == "tv":
            body["seasons"] = "all"
        data: dict[str, Any] = await self._request("POST", "/request", json=body)
        return data
