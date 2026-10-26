import numpy as np
import pytest
from PIL import Image, ImageDraw

from smriti.ml.colors import dominant_colors, name_to_lab, palette_from_hex
from smriti.ml.hashing import hash_embed
from smriti.ml.heuristics import extractive_summary, keyword_tags, normalize_tag
from smriti.ml.imaging import analyze, phash
from smriti.ml.textsig import hamming, simhash
from smriti.pipeline.chunking import chunk_html, chunk_text
from smriti.pipeline.classify import palette_codes, type_from_text, type_from_url
from smriti.pipeline.extractors.media import parse_chapters, transcript_html, youtube_id
from smriti.resurface import combine, forgetting, importance, relevance
from smriti.search.service import rrf
from smriti.urls import canonicalize, domain_of, find_urls


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("https://www.Example.com/a/?utm_source=x&b=2&a=1#frag", "https://example.com/a?a=1&b=2"),
        ("http://example.com//x//y/", "https://example.com/x/y"),
        ("https://x.com/jack/status/20?s=20", "https://twitter.com/jack/status/20"),
        ("https://youtu.be/dQw4w9WgXcQ?t=5", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
        (
            "https://m.youtube.com/watch?v=abc&feature=share&t=10",
            "https://youtube.com/watch?t=10&v=abc",
        ),
        ("https://example.com", "https://example.com/"),
    ],
)
def test_canonicalize(url: str, canonical: str) -> None:
    assert canonicalize(url) == canonical


def test_url_helpers() -> None:
    assert domain_of("https://www.nytimes.com/x") == "nytimes.com"
    assert find_urls("see https://a.com/x, and (https://b.org/y).") == [
        "https://a.com/x",
        "https://b.org/y",
    ]


def test_classify_rules() -> None:
    assert type_from_url("https://x.com/a/status/1") == "tweet"
    assert type_from_url("https://www.youtube.com/watch?v=abc") == "video"
    assert type_from_url("https://arxiv.org/pdf/2401.00001") == "pdf"
    assert type_from_url("https://a.com/cat.JPG?w=2") == "image"
    assert type_from_url("https://a.com/post") is None
    assert type_from_text("#ff0000 #00ff00, #0000ff") == "palette"
    assert type_from_text('"Simplicity is prerequisite for reliability."\n— Dijkstra') == "quote"
    assert type_from_text("Buy milk and read about hnsw") == "note"
    assert palette_codes("#fff #000 hello") is None


def test_colors_perceptual() -> None:
    blue = np.array([[40, 90, 200]] * 800 + [[245, 245, 240]] * 200, dtype=np.uint8)
    colors = dominant_colors(blue)
    assert colors[0]["weight"] == pytest.approx(0.8, abs=0.02)
    assert np.linalg.norm(np.array(colors[0]["lab"]) - np.array(name_to_lab("blue"))) < 20
    assert len(palette_from_hex(["#ff0000", "00ff00"])) == 2


def test_phash_is_stable_under_resize() -> None:
    img = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(img).rectangle((50, 50, 250, 200), fill="navy")
    small = img.resize((200, 150))
    other = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(other).ellipse((150, 20, 390, 290), fill="red")
    assert hamming(phash(img), phash(small)) <= 4
    assert hamming(phash(img), phash(other)) > 10


def test_image_analysis(tmp_path) -> None:  # noqa: ANN001
    img = Image.new("RGB", (120, 80), (220, 30, 30))
    path = tmp_path / "x.png"
    img.save(path)
    info = analyze(path.read_bytes())
    assert (info.width, info.height, info.mime) == (120, 80, "image/png")
    assert info.colors[0]["hex"].startswith("#d") or info.colors[0]["hex"].startswith("#dc")


def test_simhash_near_duplicates() -> None:
    base = " ".join(f"word{i} token{i * 7 % 13}" for i in range(400))
    near = base.replace("word3 ", "wordX ", 1)
    far = " ".join(f"other{i} thing{i % 9}" for i in range(400))
    assert hamming(simhash(base), simhash(near)) <= 3
    assert hamming(simhash(base), simhash(far)) > 10
    assert simhash("too short") is None


def test_hash_embed_is_normalized_and_lexical() -> None:
    a, b, c = (
        np.array(hash_embed(t, 384))
        for t in ("japanese carpentry joints", "carpentry in japan", "stock market")
    )
    assert abs(np.linalg.norm(a) - 1) < 1e-6
    assert a @ b > a @ c


def test_chunking_follows_headings() -> None:
    html = (
        "<h1>Title</h1><p>Intro paragraph.</p><h2>Joinery</h2><p>Dovetails are strong.</p>"
        "<blockquote><p>Measure twice.</p></blockquote><pre>code()</pre><figure><figcaption>A saw</figcaption></figure>"
    )
    chunks = chunk_html(html)
    kinds = [c.kind for c in chunks]
    assert kinds == ["section", "quote", "code", "caption", "section"] or "quote" in kinds
    joinery = [c for c in chunks if "Dovetails" in c.text][0]
    assert joinery.text.startswith("Joinery")
    long = chunk_text("Sentence one is here. " * 200, max_chars=300)
    assert all(len(c.text) <= 300 for c in long) and len(long) > 5


def test_heuristics() -> None:
    text = (
        "Japanese carpentry uses joinery instead of nails. Joinery takes years to learn. "
        "Carpenters sharpen chisels daily. The joinery in temples lasts centuries. "
        "Some joinery patterns are secret and passed down within families of carpenters."
    )
    summary, points = extractive_summary(text)
    assert summary and len(points) <= 3
    tags = keyword_tags("Japanese carpentry", text)
    assert "joinery" in tags or "carpentry" in tags
    assert normalize_tag("Machine Learning!") == "machine-learning"


def test_media_helpers() -> None:
    assert youtube_id("https://youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert youtube_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    desc = "Intro\n0:00 Start\n1:30 Middle part\n12:05 End"
    assert parse_chapters(desc) == [(0, "Start"), (90, "Middle part"), (725, "End")]
    html, text = transcript_html(
        [(0, "hello"), (70, "world"), (100, "again")], [(0, "A"), (90, "B")]
    )
    assert "<h2>A (0:00)</h2>" in html and "B (1:30)" in html and "again" in text


def test_rrf_rewards_agreement() -> None:
    scores = rrf({"keyword": ["a", "b", "c"], "semantic": ["b", "a", "d"]})
    assert scores["a"] == scores["b"] > scores["c"] > 0
    assert scores["d"] < scores["a"]


def test_resurface_scoring() -> None:
    assert forgetting(0, 0) == 0
    assert forgetting(30, 0) > forgetting(30, 2)  # each view pushes the next return out
    assert importance(True, 3, False) > importance(False, 0, False)
    assert relevance(0.3) == 0 and relevance(0.95) == 1
    assert combine(1, 1, 1, dismissals=1) == pytest.approx(combine(1, 1, 1, dismissals=0) / 2)
