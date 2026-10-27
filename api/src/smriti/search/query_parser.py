"""Split a search box query into free text plus filters: type, dates, source, color, has-note.

Rules first; a small LLM only gets the leftovers when rules miss a date-like phrase.
"blue charts from twitter last spring" -> text "charts", color blue, source twitter.com,
dates 2026-03-01..2026-05-31 (when asked in October 2026).
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from smriti.ml.colors import NAMED_COLORS

TYPE_WORDS: dict[str, str] = {
    "video": "video",
    "videos": "video",
    "youtube videos": "video",
    "talk": "video",
    "talks": "video",
    "article": "article",
    "articles": "article",
    "post": "article",
    "posts": "article",
    "blog post": "article",
    "blog posts": "article",
    "essay": "article",
    "essays": "article",
    "long read": "article",
    "long reads": "article",
    "longread": "article",
    "pdf": "pdf",
    "pdfs": "pdf",
    "paper": "pdf",
    "papers": "pdf",
    "image": "image",
    "images": "image",
    "photo": "image",
    "photos": "image",
    "picture": "image",
    "pictures": "image",
    "screenshot": "image",
    "screenshots": "image",
    "tweet": "tweet",
    "tweets": "tweet",
    "thread": "tweet",
    "threads": "tweet",
    "note": "note",
    "notes": "note",
    "quote": "quote",
    "quotes": "quote",
    "product": "product",
    "products": "product",
    "podcast": "audio",
    "podcasts": "audio",
    "episode": "audio",
    "episodes": "audio",
    "palette": "palette",
    "palettes": "palette",
    "color palette": "palette",
    "color palettes": "palette",
}
SOURCES: dict[str, str] = {
    "twitter": "twitter.com",
    "x": "twitter.com",
    "youtube": "youtube.com",
    "reddit": "reddit.com",
    "hacker news": "news.ycombinator.com",
    "hn": "news.ycombinator.com",
    "github": "github.com",
    "medium": "medium.com",
    "substack": "substack.com",
    "nytimes": "nytimes.com",
    "new york times": "nytimes.com",
    "the new yorker": "newyorker.com",
    "new yorker": "newyorker.com",
    "arxiv": "arxiv.org",
    "wikipedia": "wikipedia.org",
    "instagram": "instagram.com",
    "pinterest": "pinterest.com",
    "dribbble": "dribbble.com",
    "behance": "behance.net",
    "vimeo": "vimeo.com",
    "the guardian": "theguardian.com",
    "guardian": "theguardian.com",
    "bbc": "bbc.co.uk",
    "the verge": "theverge.com",
    "linkedin": "linkedin.com",
    "mastodon": "mastodon.social",
    "bluesky": "bsky.app",
}
MONTHS = (
    {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
    | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m and m != "May"}
    | {"sept": 9}
)
SEASONS = {
    "spring": (3, 5),
    "summer": (6, 8),
    "autumn": (9, 11),
    "fall": (9, 11),
    "winter": (12, 2),
}
UNITS = {"day": 1, "week": 7, "month": 30, "year": 365}
FILLER = {
    "from",
    "on",
    "in",
    "the",
    "my",
    "that",
    "i",
    "saved",
    "about",
    "with",
    "a",
    "an",
    "of",
    "during",
    "since",
    "via",
    "at",
    "some",
    "any",
    "all",
    "stuff",
    "things",
}
# Leftover words that suggest a date the rules could not read; then the LLM gets a try.
DATE_HINTS = re.compile(
    r"\b(ago|before|after|around|during|early|late|mid|recently|last|past|weekend|christmas|"
    r"holiday|vacation|summer|winter|spring|autumn)\b",
    re.I,
)


@dataclass
class Chip:
    kind: str  # type, date, source, color, note, tag
    label: str
    value: str
    start: int
    end: int


@dataclass
class ParsedQuery:
    raw: str
    text: str = ""
    types: list[str] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    domains: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    has_note: bool | None = None
    phrases: list[str] = field(default_factory=list)
    chips: list[Chip] = field(default_factory=list)

    @property
    def has_filters(self) -> bool:
        return bool(
            self.types
            or self.date_from
            or self.date_to
            or self.domains
            or self.colors
            or self.tags
            or self.has_note is not None
        )


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _season_range(name: str, year: int) -> tuple[date, date]:
    start_m, end_m = SEASONS[name]
    if start_m > end_m:  # winter spans the new year: Dec of `year - 1` to Feb of `year`
        return date(year - 1, 12, 1), _month_range(year, end_m)[1]
    return date(year, start_m, 1), _month_range(year, end_m)[1]


def _latest_season(name: str, today: date, *, previous: bool) -> tuple[date, date]:
    """The season occurrence that has already started; with previous=True, the one before
    the current occurrence if we are inside it."""
    year = today.year + (1 if SEASONS[name][0] == 12 and today.month == 12 else 0)
    start, end = _season_range(name, year)
    if start > today:
        start, end = _season_range(name, year - 1)
    if previous and start <= today <= end:
        start, end = _season_range(name, year - 1)
    return start, end


def _latest_month(month: int, today: date, year: int | None) -> tuple[date, date]:
    if year is None:
        year = today.year if month <= today.month else today.year - 1
    return _month_range(year, month)


class _Scanner:
    """Consumes matched spans so later rules do not reuse them."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.lower = query.lower()
        self.taken = [False] * len(query)

    def find(self, pattern: str, flags: int = re.I) -> list[re.Match[str]]:
        found = []
        for m in re.finditer(pattern, self.query, flags):
            if not any(self.taken[m.start() : m.end()]):
                found.append(m)
        return found

    def take(self, m: re.Match[str], group: int = 0) -> tuple[int, int]:
        start, end = m.span(group)
        for i in range(start, end):
            self.taken[i] = True
        return start, end

    def rest(self) -> str:
        return "".join(" " if t else c for c, t in zip(self.query, self.taken, strict=True))


def _date_rules(sc: _Scanner, pq: ParsedQuery, today: date) -> None:
    def add(m: re.Match[str], start: date, end: date, label: str) -> None:
        s, e = sc.take(m)
        pq.date_from = max(pq.date_from, start) if pq.date_from else start
        pq.date_to = min(pq.date_to, end) if pq.date_to else end
        pq.chips.append(Chip("date", label, f"{start.isoformat()}..{end.isoformat()}", s, e))

    prep = r"(?:\b(?:from|in|during|saved|on)\s+)?"
    for m in sc.find(prep + r"\btoday\b"):
        add(m, today, today, "today")
    for m in sc.find(prep + r"\byesterday\b"):
        add(m, today - timedelta(days=1), today - timedelta(days=1), "yesterday")
    for m in sc.find(prep + r"\b(this|last)\s+(week|month|year)\b"):
        which, unit = m.group(1).lower(), m.group(2).lower()
        if unit == "week":
            monday = today - timedelta(days=today.weekday())
            start = monday if which == "this" else monday - timedelta(days=7)
            end = today if which == "this" else monday - timedelta(days=1)
        elif unit == "month":
            if which == "this":
                start, end = date(today.year, today.month, 1), today
            else:
                prev = date(today.year, today.month, 1) - timedelta(days=1)
                start, end = _month_range(prev.year, prev.month)
        else:
            year = today.year if which == "this" else today.year - 1
            start, end = date(year, 1, 1), (today if which == "this" else date(year, 12, 31))
        add(m, start, end, f"{which} {unit}")
    for m in sc.find(
        r"\b(?:in\s+)?(?:the\s+)?(?:last|past)\s+(\d+|few|couple(?:\s+of)?)\s+(day|week|month|year)s?\b"
    ):
        n = {"few": 3}.get(
            m.group(1).lower(), 2 if m.group(1).lower().startswith("couple") else None
        )
        n = n or int(m.group(1))
        add(
            m,
            today - timedelta(days=n * UNITS[m.group(2).lower()]),
            today,
            f"last {n} {m.group(2)}s",
        )
    for m in sc.find(r"\b(\d+|a|an|a\s+few|a\s+couple\s+of)\s+(day|week|month|year)s?\s+ago\b"):
        word = m.group(1).lower()
        n = (
            1
            if word in ("a", "an")
            else 3
            if "few" in word
            else 2
            if "couple" in word
            else int(word)
        )
        days = n * UNITS[m.group(2).lower()]
        center = today - timedelta(days=days)
        slack = timedelta(days=max(1, days // 4))
        add(m, center - slack, min(today, center + slack), f"~{n} {m.group(2)}s ago")
    season_words = "|".join(SEASONS)
    for m in sc.find(prep + rf"\b(?:(last|this)\s+)?({season_words})(?:\s+(\d{{4}}))?\b"):
        which, name, year = (m.group(1) or "").lower(), m.group(2).lower(), m.group(3)
        if year:
            start, end = _season_range(name, int(year) + (1 if name == "winter" else 0))
        else:
            start, end = _latest_season(name, today, previous=which == "last")
        add(
            m,
            start,
            min(end, today),
            f"{which + ' ' if which else ''}{name}{' ' + year if year else ''}",
        )
    month_words = "|".join(sorted(MONTHS, key=len, reverse=True))
    for m in sc.find(
        rf"(?:\b(since|before|after)\s+|{prep})\b({month_words})\b\.?(?:\s+(\d{{4}}))?"
    ):
        rel = (m.group(1) or "").lower()
        month = MONTHS[m.group(2).lower()]
        start, end = _latest_month(month, today, int(m.group(3)) if m.group(3) else None)
        label = f"{calendar.month_name[month]}{' ' + m.group(3) if m.group(3) else ''}"
        if rel in ("since", "after"):
            add(m, start if rel == "since" else end + timedelta(days=1), today, f"{rel} {label}")
        elif rel == "before":
            add(m, date(1970, 1, 1), start - timedelta(days=1), f"before {label}")
        else:
            add(m, start, end, label)
    for m in sc.find(r"(?:\b(since|before|after|in|from|during)\s+)?\b((?:19|20)\d{2})\b"):
        rel, year = (m.group(1) or "").lower(), int(m.group(2))
        if year > today.year:
            continue
        if rel in ("since", "after"):
            add(m, date(year + (rel == "after"), 1, 1), today, f"{rel} {year}")
        elif rel == "before":
            add(m, date(1970, 1, 1), date(year - 1, 12, 31), f"before {year}")
        else:
            add(m, date(year, 1, 1), date(year, 12, 31), str(year))


def parse(query: str, now: datetime | None = None) -> ParsedQuery:
    today = (now or datetime.now()).date()
    pq = ParsedQuery(raw=query)
    sc = _Scanner(query)

    for m in sc.find(r'"([^"]+)"'):
        pq.phrases.append(m.group(1))

    _date_rules(sc, pq, today)

    for m in sc.find(
        r"\b(?:with\s+(?:a\s+|my\s+)?notes?|(?:that\s+)?i\s+(?:annotated|noted|commented\s+on)|annotated)\b"
    ):
        s, e = sc.take(m)
        pq.has_note = True
        pq.chips.append(Chip("note", "has note", "true", s, e))

    for m in sc.find(r"(?:\btagged\s+|#)([a-z0-9][\w-]*)"):
        s, e = sc.take(m)
        pq.tags.append(m.group(1).lower())
        pq.chips.append(Chip("tag", f"#{m.group(1).lower()}", m.group(1).lower(), s, e))

    source_words = "|".join(re.escape(k) for k in sorted(SOURCES, key=len, reverse=True))
    for m in sc.find(rf"\b(?:on|from|via|in)\s+({source_words})\b(?!\.\w)"):
        s, e = sc.take(m)
        domain = SOURCES[m.group(1).lower()]
        pq.domains.append(domain)
        pq.chips.append(Chip("source", domain, domain, s, e))
    for m in sc.find(r"\b(?:on|from|via|at)\s+((?:[a-z0-9-]+\.)+[a-z]{2,})\b"):
        s, e = sc.take(m)
        domain = m.group(1).lower().removeprefix("www.")
        pq.domains.append(domain)
        pq.chips.append(Chip("source", domain, domain, s, e))

    # Color words count only in lowercase: "Blue Origin" is a name, "blue chart" a color.
    color_words = "|".join(NAMED_COLORS)
    for m in sc.find(rf"\b({color_words})(?:ish)?\b", flags=0):
        s, e = sc.take(m, 1)
        name = "gray" if m.group(1) == "grey" else m.group(1)
        if name not in pq.colors:
            pq.colors.append(name)
            pq.chips.append(Chip("color", name, NAMED_COLORS[name], s, e))

    type_words = "|".join(re.escape(k) for k in sorted(TYPE_WORDS, key=len, reverse=True))
    for m in sc.find(rf"\b({type_words})\b"):
        word = m.group(1).lower()
        s, e = sc.take(m)
        t = TYPE_WORDS[word]
        if t not in pq.types:
            pq.types.append(t)
            pq.chips.append(Chip("type", t, t, s, e))

    words = re.findall(r"[\w'+#.-]+", sc.rest())
    while words and words[0].lower() in FILLER:
        words.pop(0)
    while words and words[-1].lower() in FILLER:
        words.pop()
    pq.text = " ".join(words).strip(" .,")
    pq.chips.sort(key=lambda c: c.start)
    return pq


def needs_llm(pq: ParsedQuery) -> bool:
    return bool(pq.text) and pq.date_from is None and bool(DATE_HINTS.search(pq.text))
