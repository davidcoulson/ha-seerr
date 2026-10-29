"""Find and request media; shared by the actions and the LLM tools."""

from __future__ import annotations

import re
from typing import Any

from .api import MediaResult, MediaStatus, SeerrClient, SeerrResponseError

MAX_OPTIONS = 5
# A same-title result this many times better known than the next is the one
# people mean (Oppenheimer 2023 over a 1980 mini-series).
CLEAR_FAVOURITE = 10

ALREADY_HAVE = {
    MediaStatus.AVAILABLE: "already_available",
    MediaStatus.PENDING: "already_requested",
    MediaStatus.PROCESSING: "already_requested",
}


def normalize_title(title: str, *, drop_article: bool = False) -> str:
    """Compare titles without case, punctuation and, optionally, an article."""
    title = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", title.casefold())).strip()
    return re.sub(r"^(the|a|an) ", "", title) if drop_article else title


def filter_results(
    results: list[MediaResult], media_type: str | None, year: int | None
) -> list[MediaResult]:
    """Keep the results of the given type and release year."""
    return [
        r
        for r in results
        if (media_type is None or r.media_type == media_type)
        and (year is None or r.year == year)
    ]


def pick_match(
    results: list[MediaResult], query: str
) -> tuple[MediaResult | None, list[MediaResult]]:
    """Return (the clear match, []) or (None, the options to choose from).

    A clear match is the only result, or the only one whose title equals the
    query, or the one of those with CLEAR_FAVOURITE times the votes of the
    next. Equal titles of similar standing (the UK and US Office) or no equal
    title at all are left to the caller to choose, so nothing is requested by
    guesswork.
    """
    if len(results) == 1:
        return results[0], []
    exact: list[MediaResult] = []
    # "Dig" means Dig, not The Dig; "office" still finds The Office.
    for drop_article in (False, True):
        wanted = normalize_title(query, drop_article=drop_article)
        exact = [
            r
            for r in results
            if normalize_title(r.title, drop_article=drop_article) == wanted
        ]
        if exact:
            break
    if len(exact) == 1:
        return exact[0], []
    if exact:
        top, second = sorted(exact, key=lambda r: r.vote_count, reverse=True)[:2]
        if top.vote_count >= CLEAR_FAVOURITE * max(second.vote_count, 1):
            return top, []
    return None, (exact or results)[:MAX_OPTIONS]


async def async_search(
    client: SeerrClient, query: str, media_type: str | None, year: int | None
) -> list[MediaResult]:
    """Search and filter."""
    return filter_results(await client.async_search(query), media_type, year)


async def async_request_media(
    client: SeerrClient,
    *,
    query: str | None = None,
    tmdb_id: int | None = None,
    media_type: str | None = None,
    year: int | None = None,
    is_4k: bool = False,
) -> dict[str, Any]:
    """Request a title by name, or by TMDB id and type.

    Returns a dict whose "result" is requested, already_available,
    already_requested, ambiguous (with "options") or not_found.
    """
    if tmdb_id is not None and media_type is not None:
        media: dict[str, Any] = {"tmdb_id": tmdb_id, "media_type": media_type}
    else:
        if query is None:
            raise ValueError("query, or tmdb_id with media_type, is required")
        results = await async_search(client, query, media_type, year)
        if not results:
            return {"result": "not_found", "query": query}
        match, options = pick_match(results, query)
        if match is None:
            return {
                "result": "ambiguous",
                "query": query,
                "options": [o.as_dict() for o in options],
            }
        media = match.as_dict()
        if not is_4k and (already := ALREADY_HAVE.get(match.status)):
            return {"result": already, "media": media}

    try:
        await client.async_request(media["media_type"], media["tmdb_id"], is_4k=is_4k)
    except SeerrResponseError as err:
        # Seerr answers 409 when the title is already requested.
        if err.status == 409:
            return {"result": "already_requested", "media": media}
        raise
    return {"result": "requested", "media": media}
