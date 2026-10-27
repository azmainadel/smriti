from datetime import date, datetime

import pytest

from smriti.search.query_parser import needs_llm, parse

NOW = datetime(2026, 10, 26, 12, 0)


def test_spec_example() -> None:
    pq = parse("blue charts from twitter last spring", NOW)
    assert pq.text == "charts"
    assert pq.colors == ["blue"]
    assert pq.domains == ["twitter.com"]
    assert (pq.date_from, pq.date_to) == (date(2026, 3, 1), date(2026, 5, 31))
    assert [c.kind for c in pq.chips] == ["color", "source", "date"]


def test_chip_spans_point_into_the_query() -> None:
    q = "videos about sleep from March"
    pq = parse(q, NOW)
    for chip in pq.chips:
        removed = (q[: chip.start] + q[chip.end :]).strip()
        assert chip.label.lower() not in removed.lower() or chip.kind == "type"
    assert pq.types == ["video"]
    assert (pq.date_from, pq.date_to) == (date(2026, 3, 1), date(2026, 3, 31))
    assert pq.text == "about sleep" or pq.text == "sleep"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("yesterday", (date(2026, 10, 25), date(2026, 10, 25))),
        ("last week", (date(2026, 10, 19), date(2026, 10, 25))),
        ("last month", (date(2026, 9, 1), date(2026, 9, 30))),
        ("this year", (date(2026, 1, 1), date(2026, 10, 26))),
        ("in 2024", (date(2024, 1, 1), date(2024, 12, 31))),
        ("since 2025", (date(2025, 1, 1), date(2026, 10, 26))),
        ("from December", (date(2025, 12, 1), date(2025, 12, 31))),
        ("before June 2025", (date(1970, 1, 1), date(2025, 5, 31))),
        ("last winter", (date(2025, 12, 1), date(2026, 2, 28))),
        ("this autumn", (date(2026, 9, 1), date(2026, 10, 26))),
        ("past 3 months", (date(2026, 7, 28), date(2026, 10, 26))),
    ],
)
def test_dates(query: str, expected: tuple[date, date]) -> None:
    pq = parse(f"retention {query}", NOW)
    assert (pq.date_from, pq.date_to) == expected
    assert pq.text == "retention"


def test_capitalized_color_is_a_name() -> None:
    pq = parse("Blue Origin launch", NOW)
    assert pq.colors == []
    assert pq.text == "Blue Origin launch"


def test_domain_note_and_tag_filters() -> None:
    pq = parse("essays from paulgraham.com with notes tagged startups", NOW)
    assert pq.types == ["article"]
    assert pq.domains == ["paulgraham.com"]
    assert pq.has_note is True
    assert pq.tags == ["startups"]
    assert pq.text == ""


def test_type_only_query_browses() -> None:
    pq = parse("pdfs", NOW)
    assert pq.types == ["pdf"] and pq.text == ""


def test_llm_only_for_unread_dates() -> None:
    assert not needs_llm(parse("japanese carpentry", NOW))
    assert needs_llm(parse("that recipe from around christmas", NOW))
