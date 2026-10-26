"""URL canonicalization, so the same page saved twice is recognized as one."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|ref_src|ref_url|s|si|t|"
    r"_hsenc|_hsmi|mkt_tok|yclid|spm|share_id|ncid|cmpid|smid|sref)$"
)
# Params that are part of identity on these hosts and must survive the filter above.
_KEEP_ON_HOST = {"youtube.com": {"v", "list", "t"}, "news.ycombinator.com": {"id"}}
_HOST_ALIASES = {
    "x.com": "twitter.com",
    "mobile.twitter.com": "twitter.com",
    "m.youtube.com": "youtube.com",
    "music.youtube.com": "youtube.com",
    "m.wikipedia.org": "wikipedia.org",
}
URL_RE = re.compile(r"https?://[^\s<>\"'\])]+", re.IGNORECASE)


def canonicalize(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    host = (parts.hostname or "").lower().removeprefix("www.")
    host = _HOST_ALIASES.get(host, host)
    if host.endswith(".m.wikipedia.org"):
        host = host.replace(".m.wikipedia.org", ".wikipedia.org")

    if host == "youtu.be":
        video_id = parts.path.strip("/")
        return f"https://youtube.com/watch?v={video_id}"

    keep = _KEEP_ON_HOST.get(host, set())
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k in keep or not _TRACKING_PARAMS.match(k)
    )
    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    return urlunsplit((scheme, host + port, path, urlencode(query), ""))


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return _HOST_ALIASES.get(host, host) or None


def find_urls(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text)]


def is_url(text: str) -> bool:
    text = text.strip()
    return bool(URL_RE.fullmatch(text))
