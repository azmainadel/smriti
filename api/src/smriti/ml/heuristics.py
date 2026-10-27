"""Model-free fallbacks for summary, tags and entities. Used when no LLM is configured,
so a fresh install with no models still produces useful cards and filters."""

import re
from collections import Counter

STOPWORDS = frozenset(
    """
    a about above after again against all also am an and any are aren't as at be because been
    before being below between both but by can could did do does doing don't down during each
    few for from further get got had has have having he her here hers herself him himself his
    how i if in into is isn't it it's its itself just let like made make many may me more most
    much must my myself new no nor not now of off on once one only or other our ours ourselves
    out over own per said same say says she should so some such than that the their theirs
    them themselves then there these they this those through to too two under until up upon us
    use used using very via was we were what when where which while who whom why will with
    would you your yours yourself yourselves within without also however still even really
    thing things way ways lot lots year years time times people one's first last next back
    well good great see seen show shows read
    """.split()
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]*[A-Za-z0-9+#]|[A-Za-z]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(])")
# Links and hex colors split into word-like junk ("www-youtube-com", "a506b").
_NOT_WORDS = re.compile(r"https?://\S+|www\.\S+|#[0-9A-Fa-f]{3,8}\b")
_PROPER = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:of|de|van|von|the)?\s*[A-Z][a-z]+)+|[A-Z]{2,6}\b)")


def sentences(text: str) -> list[str]:
    """Sentences within paragraphs, so a heading never fuses with the line after it."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", para).strip()
        if len(para.split()) < 6:  # headings, captions, list fragments
            continue
        out += [s.strip() for s in _SENTENCE.split(para) if _prose(s.strip())]
    return out


def _prose(s: str) -> bool:
    """Reject citations, captions and data rows: real sentences start with a letter and
    are mostly letters."""
    if not 30 <= len(s) <= 400 or not s[0].isalpha():
        return False
    letters = sum(c.isalpha() or c.isspace() for c in s)
    return letters / len(s) > 0.85


def _freqs(text: str) -> Counter[str]:
    return Counter(
        w.lower() for w in _WORD.findall(text) if w.lower() not in STOPWORDS and len(w) > 2
    )


def extractive_summary(text: str, description: str | None = None) -> tuple[str, list[str]]:
    """One summary sentence and up to 3 key points, picked by word-frequency score."""
    sents = sentences(text[:50_000])
    if not sents:
        short = (description or text).strip()[:280]
        return short, []
    freqs = _freqs(text)
    top = max(freqs.values(), default=1)

    def score(s: str) -> float:
        words = [w.lower() for w in _WORD.findall(s)]
        return sum(freqs.get(w, 0) / top for w in words) / (len(words) ** 0.5 or 1)

    summary = description.strip() if description and len(description) > 40 else sents[0]
    ranked = sorted((s for s in sents if s != summary), key=score, reverse=True)[:3]
    # Key points read best in document order.
    points = [s for s in dict.fromkeys(sents) if s in ranked][:3]
    return summary[:400], points


# Words frequent in any text that say nothing about a topic. Kept out of tags only;
# summaries still use them to score sentences.
GENERIC = frozenset(
    """
    don doesn didn isn wasn aren won wouldn couldn shouldn haven hasn hadn ll ve re
    often always never sometimes usually probably maybe perhaps quite rather simply actually
    want wants wanted need needs needed seem seems seemed seen try tried trying get gets got
    going go goes went come comes came give gives gave take takes took put puts keep keeps
    know knows knew think thinks thought feel feels felt look looks looked find finds found
    tell tells told ask asks asked work works working worked call called mean means meant
    best better good bad big small large long short high low new old right wrong real true
    able kind sort part lot lots bit thing things something anything everything nothing
    someone anyone everyone people person way ways day days time times year years
    first second last next different same other others another every each many few much
    important possible likely clear hard easy sure whole enough less least most more
    start started starts end ended begin began made make makes making use used uses using
    said says say saying let lets help helps hand case point fact idea ideas example
    done built interested become became include includes including called known based
    citation citations retrieved archived original edit isbn wikipedia pdf page pages
    """.split()
)


def keyword_tags(title: str, text: str, limit: int = 6) -> list[str]:
    title, text = _NOT_WORDS.sub(" ", title), _NOT_WORDS.sub(" ", text)
    freqs = _freqs(f"{title} {title} {title} {text[:30_000]}")
    for word in GENERIC:
        freqs.pop(word, None)
    bigrams: Counter[str] = Counter()
    words = [w.lower() for w in _WORD.findall(text[:30_000])]
    for a, b in zip(words, words[1:], strict=False):
        if (
            a not in STOPWORDS | GENERIC
            and b not in STOPWORDS | GENERIC
            and len(a) > 2
            and len(b) > 2
        ):
            bigrams[f"{a} {b}"] += 1
    candidates = [(w, c) for w, c in freqs.most_common(40) if not w.isdigit()]
    candidates += [(b, c * 2) for b, c in bigrams.most_common(10) if c >= 3]
    ranked = sorted(candidates, key=lambda x: -x[1])
    tags: list[str] = []
    seen: set[str] = set()
    for word, _ in ranked:
        tag = normalize_tag(word)
        stem = "-".join(p.rstrip("s") for p in tag.split("-"))  # gardens and garden are one tag
        if tag and stem not in seen:
            seen.add(stem)
            tags.append(tag)
    # A two-word tag makes its parts redundant: keep "japanese-carpentry", drop "carpentry".
    parts = {p for t in tags if "-" in t for p in t.split("-")}
    return [t for t in tags if t not in parts][:limit]


def normalize_tag(tag: str) -> str:
    tag = re.sub(r"[^a-z0-9+#]+", "-", tag.lower()).strip("-")
    return tag[:40]


# Acronyms that show up in references and markup, not in what a page is about.
_JUNK_NAMES = frozenset(
    "ISBN ISSN DOI PDF HTML URL HTTP HTTPS API FAQ RSS CSS JSON XML USD EUR GMT UTC AM PM TV OK "
    "ID UK US USA EU CEO".split()
)


def proper_nouns(text: str, limit: int = 12) -> list[str]:
    counts = Counter(m.strip() for m in _PROPER.findall(text[:50_000]))
    names = []
    for name, c in counts.most_common(limit * 3):
        if name in _JUNK_NAMES or name.lower() in STOPWORDS:
            continue
        # Single acronyms are noisy; ask more of them than of multi-word names.
        if c >= (3 if name.isupper() else 2):
            names.append(name)
    return names[:limit]
