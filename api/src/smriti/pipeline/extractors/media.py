"""YouTube videos and audio: transcript from captions, else local Whisper; chapters; key frames."""

import asyncio
import html as htmllib
import json
import logging
import re
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from smriti.config import get_settings
from smriti.models import ItemType
from smriti.pipeline.extractors.base import Extraction

log = logging.getLogger(__name__)
CHAPTER_RE = re.compile(r"^\s*\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?\s*[-–—:]?\s*(.+)$")
PLAYER_RE = re.compile(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*(?:var\s|</script>)", re.S)


def youtube_id(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.endswith("youtu.be"):
        return parts.path.strip("/") or None
    if v := parse_qs(parts.query).get("v"):
        return v[0]
    if m := re.search(r"/(?:shorts|live|embed)/([\w-]{11})", parts.path):
        return m.group(1)
    return None


def to_seconds(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    return (
        f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    )


def parse_chapters(description: str) -> list[tuple[int, str]]:
    chapters = [
        (to_seconds(m.group(1)), m.group(2).strip())
        for line in description.splitlines()
        if (m := CHAPTER_RE.match(line))
    ]
    # YouTube only treats a list as chapters if it starts at 0:00 and has 3+ entries.
    return chapters if len(chapters) >= 3 and chapters[0][0] == 0 else []


def transcript_html(
    segments: list[tuple[float, str]], chapters: list[tuple[int, str]], window_s: int = 60
) -> tuple[str, str]:
    """Group caption segments into ~1 minute paragraphs under chapter headings."""
    bounds = chapters or [(0, "")]
    parts: list[str] = []
    plain: list[str] = []
    for ci, (start, title) in enumerate(bounds):
        end = bounds[ci + 1][0] if ci + 1 < len(bounds) else float("inf")
        in_chapter = [(t, s) for t, s in segments if start <= t < end]
        if title:
            parts.append(f"<h2>{htmllib.escape(title)} ({fmt_time(start)})</h2>")
            plain.append(title)
        para: list[str] = []
        para_start = in_chapter[0][0] if in_chapter else start
        for t, s in in_chapter:
            if para and t - para_start >= window_s:
                text = " ".join(para)
                parts.append(
                    f'<p data-t="{int(para_start)}">[{fmt_time(para_start)}] {htmllib.escape(text)}</p>'
                )
                plain.append(text)
                para, para_start = [], t
            para.append(s.strip())
        if para:
            text = " ".join(para)
            parts.append(
                f'<p data-t="{int(para_start)}">[{fmt_time(para_start)}] {htmllib.escape(text)}</p>'
            )
            plain.append(text)
    return "\n".join(parts), "\n\n".join(plain)


async def _youtube_page(client: httpx.AsyncClient, video_id: str) -> dict[str, Any]:
    r = await client.get(
        f"https://www.youtube.com/watch?v={video_id}", headers={"Accept-Language": "en"}
    )
    if m := PLAYER_RE.search(r.text):
        try:
            return json.loads(m.group(1)).get("videoDetails", {})
        except json.JSONDecodeError:
            pass
    return {}


def _captions(video_id: str) -> list[tuple[float, str]]:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    listing = api.list(video_id)
    try:
        transcript = listing.find_manually_created_transcript(["en"])
    except Exception:  # noqa: BLE001 - fall through to any available transcript
        transcript = next(iter(listing))
    return [(snip.start, snip.text) for snip in transcript.fetch()]


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _whisper(data: bytes, suffix: str) -> tuple[list[tuple[float, str]], float, str | None]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        segments, info = model.transcribe(f.name, vad_filter=True)
        return [(seg.start, seg.text) for seg in segments], info.duration, info.language


async def extract_youtube(url: str) -> Extraction:
    video_id = youtube_id(url)
    if not video_id:
        raise ValueError(f"no video id in {url}")
    s = get_settings()
    async with httpx.AsyncClient(
        timeout=s.fetch_timeout_s, headers={"User-Agent": s.user_agent}
    ) as c:
        oembed_r, details = await asyncio.gather(
            c.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            ),
            _youtube_page(c, video_id),
        )
    oembed = oembed_r.json() if oembed_r.status_code == 200 else {}
    description = details.get("shortDescription", "")
    chapters = parse_chapters(description)

    try:
        segments = await asyncio.to_thread(_captions, video_id)
        source = "captions"
    except Exception as e:  # noqa: BLE001 - many failure modes: disabled, region, rate limit
        log.info("no captions for %s: %s", video_id, e)
        segments, source = [], None

    html, text = transcript_html(segments, chapters) if segments else ("", "")
    if description:
        html = f"<h2>Description</h2>{_paras(description)}\n{html}"
        text = f"{description}\n\n{text}"
    frames = [f"https://i.ytimg.com/vi/{video_id}/{n}.jpg" for n in (1, 2, 3)]
    return Extraction(
        title=oembed.get("title") or details.get("title"),
        text=text,
        html=html,
        site_name="YouTube",
        type=ItemType.video,
        image_urls=[f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", *frames],
        meta={
            k: v
            for k, v in {
                "video_id": video_id,
                "channel": oembed.get("author_name") or details.get("author"),
                "duration": int(details["lengthSeconds"]) if details.get("lengthSeconds") else None,
                "chapters": [{"t": t, "title": title} for t, title in chapters] or None,
                "transcript": source,
            }.items()
            if v
        },
    )


async def extract_audio(data: bytes, suffix: str, title: str | None) -> Extraction:
    if not whisper_available():
        return Extraction(title=title, type=ItemType.audio, meta={"transcript": None})
    segments, duration, lang = await asyncio.to_thread(_whisper, data, suffix)
    html, text = transcript_html(segments, [])
    return Extraction(
        title=title,
        text=text,
        html=html,
        lang=lang,
        meta={"duration": int(duration), "transcript": "whisper"},
    )


def _paras(text: str) -> str:
    return "".join(f"<p>{htmllib.escape(p)}</p>" for p in text.split("\n\n") if p.strip())
