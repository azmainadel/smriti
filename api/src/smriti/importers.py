"""One-time importers: browser bookmarks (Netscape HTML, which Pocket also exports),
Pocket CSV and Raindrop CSV."""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime

from lxml import html as lxml_html
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smriti import items as item_service
from smriti.models import Item
from smriti.schemas import ItemCreate
from smriti.urls import canonicalize


@dataclass
class Bookmark:
    url: str
    title: str | None = None
    note: str | None = None
    tags: list[str] = field(default_factory=list)
    saved_at: datetime | None = None


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        n = int(value)
        # Some exporters write milliseconds or microseconds since the epoch.
        while n > 10**11:
            n //= 1000
        return datetime.fromtimestamp(n, UTC)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _tags(value: str | None, sep: str = ",") -> list[str]:
    return [t.strip() for t in (value or "").replace("|", sep).split(sep) if t.strip()]


def parse_netscape(doc: str) -> list[Bookmark]:
    tree = lxml_html.fromstring(doc)
    out = []
    for a in tree.iterfind(".//a"):
        href = a.get("href") or ""
        if not href.startswith(("http://", "https://")):
            continue
        # Folder names become tags: the DT/DL nesting holds the H3 headings.
        folders = [
            h3.text_content().strip()
            for dl in a.iterancestors("dl")
            for h3 in [dl.getprevious()]
            if h3 is not None and h3.tag == "h3" and h3.text_content().strip()
        ]
        dd = a.getparent().getnext() if a.getparent() is not None else None
        note = dd.text_content().strip() if dd is not None and dd.tag == "dd" else None
        out.append(
            Bookmark(
                url=href,
                title=a.text_content().strip() or None,
                note=note or None,
                tags=_tags(a.get("tags"))
                + [
                    f
                    for f in reversed(folders)
                    if f.lower()
                    not in (
                        "bookmarks bar",
                        "bookmarks menu",
                        "other bookmarks",
                        "bookmarks toolbar",
                    )
                ],
                saved_at=_ts(a.get("add_date") or a.get("time_added")),
            )
        )
    return out


def parse_csv(doc: str) -> tuple[str, list[Bookmark]]:
    reader = csv.DictReader(io.StringIO(doc))
    fields = {f.lower() for f in reader.fieldnames or []}
    out = []
    if {"url", "excerpt"} <= fields or "highlights" in fields:  # Raindrop
        for row in reader:
            note = "\n\n".join(
                x for x in (row.get("note"), row.get("highlights")) if x and x.strip()
            )
            out.append(
                Bookmark(
                    row["url"],
                    row.get("title") or None,
                    note or None,
                    _tags(row.get("tags")) + _tags(row.get("folder"), "/"),
                    _ts(row.get("created")),
                )
            )
        return "raindrop", out
    if {"url", "time_added"} <= fields:  # Pocket
        for row in reader:
            out.append(
                Bookmark(
                    row["url"],
                    row.get("title") or None,
                    None,
                    _tags(row.get("tags"), "|"),
                    _ts(row.get("time_added")),
                )
            )
        return "pocket", out
    if "url" in fields:
        for row in reader:
            out.append(
                Bookmark(
                    row["url"],
                    row.get("title") or None,
                    row.get("note") or None,
                    _tags(row.get("tags")),
                    _ts(row.get("created") or row.get("date")),
                )
            )
        return "csv", out
    raise ValueError("CSV needs a url column")


def parse_any(filename: str, data: bytes) -> tuple[str, list[Bookmark]]:
    doc = data.decode("utf-8", "replace")
    head = doc[:2000].lower()
    if (
        "<!doctype netscape-bookmark-file" in head
        or "<dl" in head
        or filename.lower().endswith((".html", ".htm"))
    ):
        return "bookmarks-html", parse_netscape(doc)
    return parse_csv(doc)


async def import_bookmarks(session: AsyncSession, bookmarks: list[Bookmark]) -> tuple[int, int]:
    """Create items, skipping URLs already saved. Returns (created, skipped)."""
    existing = set(
        (
            await session.execute(select(Item.canonical_url).where(Item.canonical_url.is_not(None)))
        ).scalars()
    )
    created = skipped = 0
    for b in bookmarks:
        try:
            canonical = canonicalize(b.url)
        except ValueError:
            skipped += 1
            continue
        if canonical in existing:
            skipped += 1
            continue
        existing.add(canonical)
        await item_service.save(
            session,
            ItemCreate(
                url=b.url,
                title=b.title,
                note=b.note,
                tags=b.tags[:20],
                capture="import",
                saved_at=b.saved_at,
            ),
        )
        created += 1
        if created % 200 == 0:
            await session.commit()
    await session.commit()
    return created, skipped
