"""Tweets and threads. X has no stable public API, so this parses either the page the
extension rendered or the fxtwitter mirror, and walks reply chains to unroll threads."""

import html as htmllib
import re
from typing import Any

import httpx

from smriti.config import get_settings
from smriti.models import ItemType
from smriti.pipeline.extractors import html as h
from smriti.pipeline.extractors.base import Extraction

STATUS_RE = re.compile(r"(?:twitter|x)\.com/([^/]+)/status/(\d+)", re.I)
MAX_THREAD = 25


def _post_html(t: dict[str, Any], quote: dict[str, Any] | None) -> str:
    body = htmllib.escape(t["text"]).replace("\n", "<br>")
    out = f"<p>{body}</p>"
    if quote:
        out += (
            f"<blockquote><p><strong>@{htmllib.escape(quote['handle'])}</strong>: "
            f"{htmllib.escape(quote['text'])}</p></blockquote>"
        )
    return out


def _simplify(raw: dict[str, Any]) -> dict[str, Any]:
    media = raw.get("media") or {}
    photos = [p["url"] for p in media.get("photos", []) if p.get("url")]
    photos += [v["thumbnail_url"] for v in media.get("videos", []) if v.get("thumbnail_url")]
    author = raw.get("author") or {}
    return {
        "id": raw.get("id"),
        "text": raw.get("text") or "",
        "handle": author.get("screen_name") or "",
        "name": author.get("name") or "",
        "avatar": author.get("avatar_url"),
        "created_at": raw.get("created_at"),
        "media": photos,
        "reply_to_handle": raw.get("replying_to"),
        "reply_to_id": raw.get("replying_to_status"),
        "quote": _simplify(raw["quote"]) if raw.get("quote") else None,
    }


async def _fx(client: httpx.AsyncClient, handle: str, status_id: str) -> dict[str, Any] | None:
    r = await client.get(f"https://api.fxtwitter.com/{handle}/status/{status_id}")
    if r.status_code != 200:
        return None
    tweet = r.json().get("tweet")
    return _simplify(tweet) if tweet else None


async def _thread_from_api(url: str) -> list[dict[str, Any]]:
    m = STATUS_RE.search(url)
    if not m:
        return []
    handle, status_id = m.groups()
    s = get_settings()
    async with httpx.AsyncClient(
        timeout=s.fetch_timeout_s, headers={"User-Agent": s.user_agent}
    ) as c:
        tweet = await _fx(c, handle, status_id)
        if not tweet:
            return []
        thread = [tweet]
        # Self-replies above the saved tweet are the earlier parts of the thread.
        while (
            len(thread) < MAX_THREAD
            and thread[0]["reply_to_id"]
            and (thread[0]["reply_to_handle"] or "").lower() == tweet["handle"].lower()
        ):
            parent = await _fx(c, tweet["handle"], thread[0]["reply_to_id"])
            if not parent:
                break
            thread.insert(0, parent)
        return thread


def _thread_from_page(doc: str) -> list[dict[str, Any]]:
    """Parse tweets from the DOM the extension captured on x.com."""
    tree = h.parse(doc)
    posts = []
    for art in tree.xpath('//article[@data-testid="tweet"]'):
        text_el = art.xpath('.//div[@data-testid="tweetText"]')
        user = art.xpath('.//div[@data-testid="User-Name"]//span')
        handle = next((s.text_content()[1:] for s in user if s.text_content().startswith("@")), "")
        posts.append(
            {
                "text": text_el[0].text_content() if text_el else "",
                "handle": handle,
                "name": user[0].text_content() if user else handle,
                "media": [
                    i.get("src") for i in art.xpath('.//div[@data-testid="tweetPhoto"]//img')
                ],
                "quote": None,
            }
        )
    if not posts:
        return []
    # Keep the leading run of posts by the first author: that is the thread.
    first = posts[0]["handle"]
    return [p for p in posts if p["handle"] == first][:MAX_THREAD]


async def extract_tweet(url: str, page_html: str | None) -> Extraction:
    thread = _thread_from_page(page_html) if page_html else []
    if not thread:
        thread = await _thread_from_api(url)
    if not thread:
        raise ValueError(f"could not read tweet {url}")

    head = thread[0]
    text = "\n\n".join(
        t["text"]
        + (f"\n\n> @{t['quote']['handle']}: {t['quote']['text']}" if t.get("quote") else "")
        for t in thread
    )
    html = "\n".join(_post_html(t, t.get("quote")) for t in thread)
    media = [m for t in thread for m in t["media"]]
    title = f"{head['name']} on X: {head['text'][:80]}".strip()
    return Extraction(
        title=title,
        text=text,
        html=html,
        site_name="X",
        type=ItemType.tweet,
        image_urls=media[:8],
        meta={
            "author": head["name"],
            "handle": head["handle"],
            "avatar": head.get("avatar"),
            "posts": len(thread),
            "published": head.get("created_at"),
            "tweet_text": head["text"],
        },
    )
