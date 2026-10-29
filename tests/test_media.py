"""Tests for choosing which search result is meant."""

from __future__ import annotations

import pytest

from custom_components.seerr.api import MediaResult, MediaStatus
from custom_components.seerr.media import filter_results, normalize_title, pick_match

from .conftest import DIG_RESULTS, item

DIG = [MediaResult.from_api(i) for i in DIG_RESULTS if i["mediaType"] != "person"]


def titles(results: list[MediaResult]) -> list[tuple[str, int | None, str]]:
    return [(r.title, r.year, r.media_type) for r in results]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("The Office", "office"), ("Dig!", "dig"), ("  A  Quiet Place ", "quiet place")],
)
def test_normalize_title(raw: str, expected: str) -> None:
    assert normalize_title(raw, drop_article=True) == expected
    assert normalize_title("The Office") == "the office"


def test_from_api() -> None:
    result = DIG[3]
    assert (result.tmdb_id, result.year, result.status) == (
        816956,
        2022,
        MediaStatus.AVAILABLE,
    )
    assert DIG[0].status is MediaStatus.UNKNOWN
    odd = MediaResult.from_api(
        {"id": 1, "mediaType": "tv", "name": "X", "mediaInfo": {"status": 99}}
    )
    assert (odd.year, odd.status) == (None, MediaStatus.UNKNOWN)


def test_same_title_of_similar_standing_is_ambiguous() -> None:
    match, options = pick_match(DIG, "Dig", 2030)
    assert match is None
    assert titles(options) == [
        ("Dig", 2015, "tv"),
        ("Dig", 2026, "tv"),
        ("Dig", 2022, "movie"),
    ]


@pytest.mark.parametrize(("year", "tmdb_id"), [(2025, 290826), (2027, 290826)])
def test_new_release_is_meant(year: int, tmdb_id: int) -> None:
    # Coming soon (2025), or out last year (2027), beats the better-known 2015 show.
    match, _ = pick_match(DIG, "Dig", year)
    assert match is not None
    assert match.tmdb_id == tmdb_id


def test_singleton_with_another_title_is_not_a_match() -> None:
    match, options = pick_match(DIG[2:3], "Dig Deep")
    assert match is None
    assert [o.tmdb_id for o in options] == [532865]


def test_type_and_year_narrow_to_one() -> None:
    match, options = pick_match(filter_results(DIG, "tv", 2015), "Dig")
    assert match is not None
    assert (match.tmdb_id, options) == (62120, [])


def test_far_better_known_title_wins() -> None:
    # Once neither is new: Dig 2015 (91 votes) over Dig 2026 (0 votes).
    match, _ = pick_match(filter_results(DIG, "tv", None), "dig", 2030)
    assert match is not None
    assert match.tmdb_id == 62120
    oppenheimer = [
        MediaResult.from_api(item(872585, "movie", "Oppenheimer", "2023-07-19", 12784)),
        MediaResult.from_api(item(17024, "tv", "Oppenheimer", "1980-01-01", 13)),
    ]
    match, _ = pick_match(oppenheimer, "oppenheimer")
    assert match is not None
    assert match.tmdb_id == 872585


def test_only_exact_title_wins() -> None:
    match, _ = pick_match(DIG, "The Dig")
    assert match is not None
    assert match.tmdb_id == 532865


def test_article_only_matters_when_nothing_else_matches() -> None:
    match, _ = pick_match(DIG, "dig", 2030)
    assert match is None
    match, _ = pick_match(filter_results(DIG, "movie", 2021), "Dig")
    assert match is not None
    office = [
        MediaResult.from_api(item(2316, "tv", "The Office", "2005-03-24", 5643)),
        MediaResult.from_api(item(2996, "tv", "The Office", "2001-07-09", 1014)),
        MediaResult.from_api(item(9, "tv", "Office Girls", "2011-01-01", 3)),
    ]
    match, options = pick_match(office, "office")
    assert match is None
    assert [o.tmdb_id for o in options] == [2316, 2996]


def test_no_exact_title_offers_the_top_results() -> None:
    match, options = pick_match(DIG, "Digging")
    assert match is None
    assert len(options) == 4
