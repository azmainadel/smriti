from pathlib import Path

from smriti.pipeline.extractors.article import extract_article, strip_site_suffix
from smriti.pipeline.extractors.pdf import parse_pdf
from smriti.pipeline.extractors.simple import extract_note, palette_from_url
from smriti.pipeline.extractors.tweet import _thread_from_page
from smriti.routers.inbound import normalize, plan

FIXTURES = Path(__file__).parent / "fixtures"


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for text in pages:
        content = f"BT /F1 14 Tf 72 720 Td ({text}) Tj ET".encode()
        page_id, content_id = len(objects) + 1, len(objects) + 2
        kids.append(f"{page_id} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_pdf_pages_and_thumbnail() -> None:
    ex = parse_pdf(
        make_pdf(
            [
                "Attention is all you need, a study of transformers",
                "Results on translation benchmarks",
            ]
        )
    )
    assert ex.meta["pages"] == 2
    assert "transformers" in ex.text and "translation" in ex.text
    assert '<h2 data-page="2">Page 2</h2>' in ex.html
    assert ex.images and ex.images[0].kind == "thumbnail"


def test_article_keeps_structure_and_drops_chrome() -> None:
    ex = extract_article((FIXTURES / "article.html").read_text(), "https://woodworking.example/a")
    assert ex.title == "The quiet craft of Japanese carpentry"
    assert "<h2>Joints that move</h2>" in ex.html or "Joints that move" in ex.html
    assert "Subscribe to our newsletter" not in ex.text
    assert ex.canonical_url == "https://woodworking.example/articles/japanese-carpentry"
    assert ex.meta["words"] > 150


def test_lazy_images_promoted() -> None:
    html = (
        "<html><body><article><h1>T</h1><p>" + "Long text here. " * 60 + "</p>"
        '<img src="data:image/gif;base64,R0" data-src="https://cdn.example/real.jpg"></article></body></html>'
    )
    ex = extract_article(html, "https://example.com/post")
    assert "https://cdn.example/real.jpg" in ex.image_urls


def test_quote_and_palette() -> None:
    ex = extract_note('"Simplicity is prerequisite for reliability."\n— Edsger Dijkstra', "quote")
    assert ex.meta == {
        "attribution": "Edsger Dijkstra",
        "quote": "Simplicity is prerequisite for reliability.",
    }
    pal = palette_from_url("https://coolors.co/264653-2a9d8f-e9c46a")
    assert pal and pal.palette == ["#264653", "#2a9d8f", "#e9c46a"]


def test_tweet_thread_from_rendered_page() -> None:
    page = """
    <article data-testid="tweet"><div data-testid="User-Name"><span>Ada</span><span>@ada</span></div>
      <div data-testid="tweetText">1/ Notes on analytical engines</div></article>
    <article data-testid="tweet"><div data-testid="User-Name"><span>Ada</span><span>@ada</span></div>
      <div data-testid="tweetText">2/ They weave algebra like looms weave flowers</div>
      <div data-testid="tweetPhoto"><img src="https://pbs.example/1.jpg"></div></article>
    <article data-testid="tweet"><div data-testid="User-Name"><span>Bob</span><span>@bob</span></div>
      <div data-testid="tweetText">great thread</div></article>"""
    thread = _thread_from_page(page)
    assert [t["text"][:2] for t in thread] == ["1/", "2/"]
    assert thread[1]["media"] == ["https://pbs.example/1.jpg"]


def test_email_planning() -> None:
    mail = normalize(
        {
            "subject": "Fwd: two links",
            "text": "https://a.example/x\nhttps://b.example/y\nboth on focus\n\n-- \nSent from phone",
        }
    )
    items = plan(mail)
    assert [str(i.url) for i in items] == ["https://a.example/x", "https://b.example/y"]
    assert items[0].note == "both on focus"
    note = plan(normalize({"subject": "Idea", "text": "Make a garden planner"}))
    assert note[0].text == "Make a garden planner" and note[0].title == "Idea"


def test_layout_tables_unwrap_and_icons_go() -> None:
    from smriti.pipeline.extractors.html import clean_layout

    html = (
        '<table><tr><td><img src="/nav.gif"></td><td><img src="/trans_1x1.gif"></td></tr></table>'
        "<table><tr><td><p>July 2023</p><p>Essay text.</p></td></tr></table>"
        "<table><tr><th>Model</th><th>Score</th></tr><tr><td>A</td><td>1</td></tr></table>"
    )
    out = clean_layout(html, "https://example.com/essay", {"https://example.com/nav.gif"})
    assert "nav.gif" not in out and "trans_1x1" not in out
    assert "<div><p>July 2023</p><p>Essay text.</p></div>" in out
    assert out.count("<table") == 1  # the data table stays


def test_site_suffix_leaves_titles() -> None:
    wiki = "https://en.wikipedia.org/wiki/Japanese_garden"
    assert strip_site_suffix("Japanese garden - Wikipedia", None, wiki) == "Japanese garden"
    assert (
        strip_site_suffix("How it works | The Verge", "The Verge", "https://x.com")
        == "How it works"
    )
    assert strip_site_suffix("Rust vs Go - a comparison", None, wiki) == "Rust vs Go - a comparison"
