import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw, ImageFont

from smriti.worker import run_until_idle

FIXTURES = Path(__file__).parent / "fixtures"


async def save(client: AsyncClient, **body) -> dict:  # noqa: ANN003
    r = await client.post("/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_requires_token(client: AsyncClient) -> None:
    r = await client.get("/items", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    r = await client.post("/auth/tokens", json={"name": "x", "secret": "wrong"})
    assert r.status_code == 401


async def test_save_note_returns_pending_then_ready(client: AsyncClient) -> None:
    item = await save(
        client, text="Remember: hinoki cypress gets stronger for 200 years after cutting."
    )
    assert item["status"] == "pending" and item["type"] == "note"
    await run_until_idle()
    detail = (await client.get(f"/items/{item['id']}")).json()
    assert detail["status"] == "ready"
    assert "hinoki" in detail["content_html"]
    assert {e["step"] for e in detail["enrichments"]} >= {"summary", "tags", "embeddings", "dedup"}


async def test_extension_article_end_to_end(client: AsyncClient) -> None:
    html = (FIXTURES / "article.html").read_text()
    item = await save(
        client,
        url="https://woodworking.example/articles/japanese-carpentry?utm_source=newsletter",
        html=html,
        title="The quiet craft of Japanese carpentry | Woodworking Weekly",
        note="for the shed project",
        capture="extension",
    )
    await run_until_idle()
    d = (await client.get(f"/items/{item['id']}")).json()
    assert d["status"] == "ready", d["error"]
    assert d["type"] == "article"
    assert d["title"] == "The quiet craft of Japanese carpentry"
    assert d["site_name"] == "Woodworking Weekly"
    assert "Joints that move" in d["content_html"]
    assert "newsletter" not in d["content_html"].lower()
    assert d["summary"]
    assert d["tags"], "heuristic tags expected without an LLM"
    assert d["archive_url"]

    # Keyword, as-you-type prefix, and the note all find it.
    for q in ("kanawa tsugi", "miyadai", "shed project"):
        r = (await client.get("/search", params={"q": q})).json()
        assert r["hits"] and r["hits"][0]["item"]["id"] == item["id"], q
    hit = (await client.get("/search", params={"q": "kanawa joint"})).json()["hits"][0]
    assert "<mark>" in (hit["highlight"] or "")

    # Archived HTML is served through a signed URL, sandboxed.
    path = d["archive_url"].split("http://localhost:8000", 1)[1]
    archived = await client.get(path)
    assert archived.status_code == 200 and "sandbox" in archived.headers["content-security-policy"]
    assert (await client.get(path.split("&sig=")[0] + "&sig=bad")).status_code == 403


async def test_product_from_structured_data(client: AsyncClient) -> None:
    item = await save(
        client,
        url="https://tools.example/kanna",
        html=(FIXTURES / "product.html").read_text(),
        capture="extension",
    )
    await run_until_idle()
    d = (await client.get(f"/items/{item['id']}")).json()
    assert d["type"] == "product"
    assert d["title"] == "Kanna Japanese hand plane, 70mm"
    assert d["meta"]["price"] == "89.00" and d["meta"]["currency"] == "USD"


async def test_filters_and_browse(client: AsyncClient) -> None:
    await save(client, text="#1e63d0 #0f2a5e #a8c5ff")  # a blue palette
    await save(client, text="#d32f2f #ff7f50")  # a red one
    await save(client, text='"Make it work, make it right, make it fast."\n— Kent Beck')
    await run_until_idle()

    r = (await client.get("/search", params={"q": "palettes"})).json()
    assert {h["item"]["type"] for h in r["hits"]} == {"palette"} and len(r["hits"]) == 2
    assert r["chips"][0]["kind"] == "type"

    r = (await client.get("/search", params={"q": "blue palettes"})).json()
    assert len(r["hits"]) == 1 and "#1e63d0" in json.dumps(r["hits"][0]["item"]["palette"])

    r = (await client.get("/search", params={"q": "quotes about making"})).json()
    assert r["hits"][0]["item"]["type"] == "quote"
    assert r["hits"][0]["item"]["meta"]["attribution"] == "Kent Beck"


async def test_no_results_falls_back_without_filters(client: AsyncClient) -> None:
    await save(client, text="Notes on retrieval augmented generation and rerankers")
    await run_until_idle()
    r = (await client.get("/search", params={"q": "retrieval videos"})).json()
    assert r["fallback"] is True and r["hits"]


async def test_patch_tags_note_and_events(client: AsyncClient) -> None:
    item = await save(client, text="Spaced repetition beats rereading for long-term memory.")
    await run_until_idle()
    r = await client.patch(
        f"/items/{item['id']}",
        json={"note": "use for flashcards app", "tags": ["Learning", "memory"]},
    )
    assert r.status_code == 200
    assert r.json()["tags"] == ["learning", "memory"]
    hits = (await client.get("/search", params={"q": "flashcards"})).json()["hits"]
    assert hits and hits[0]["item"]["id"] == item["id"]
    tagged = (await client.get("/items", params={"tag": "learning"})).json()["items"]
    assert [i["id"] for i in tagged] == [item["id"]]

    assert (
        await client.post("/events", json={"item_id": item["id"], "kind": "open"})
    ).status_code == 204
    assert (await client.get(f"/items/{item['id']}")).json()["open_count"] == 1


async def test_pagination_and_delete(client: AsyncClient) -> None:
    ids = [(await save(client, text=f"note number {i}"))["id"] for i in range(5)]
    page1 = (await client.get("/items", params={"limit": 2})).json()
    page2 = (await client.get("/items", params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    page3 = (await client.get("/items", params={"limit": 2, "cursor": page2["next_cursor"]})).json()
    seen = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert seen == list(reversed(ids)) and page3["next_cursor"] is None
    assert (await client.delete(f"/items/{ids[0]}")).status_code == 204
    assert (await client.get(f"/items/{ids[0]}")).status_code == 404


async def test_duplicate_url_is_linked(client: AsyncClient) -> None:
    html = (FIXTURES / "article.html").read_text()
    first = await save(
        client,
        url="https://woodworking.example/articles/japanese-carpentry",
        html=html,
        capture="extension",
    )
    await run_until_idle()
    second = await save(
        client,
        url="https://www.woodworking.example/articles/japanese-carpentry/?utm_campaign=x",
        html=html,
        capture="extension",
    )
    await run_until_idle()
    d = (await client.get(f"/items/{second['id']}")).json()
    assert d["duplicate_of"] == first["id"]
    grid = (await client.get("/items")).json()["items"]
    assert [i["id"] for i in grid] == [first["id"]]


async def test_image_upload_ocr_colors(client: AsyncClient) -> None:
    img = Image.new("RGB", (900, 300), (30, 99, 208))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 80, 860, 220), fill="white")
    draw.text((60, 110), "RETENTION CHART Q3", fill="black", font=ImageFont.load_default(size=56))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = await client.post(
        "/items",
        files={"file": ("chart.png", buf.getvalue(), "image/png")},
        data={"note": "from the board deck"},
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["type"] == "image"
    await run_until_idle()
    d = (await client.get(f"/items/{item['id']}")).json()
    assert d["status"] == "ready"
    assert d["palette"] and d["lead_image"]
    assert any("RETENTION" in (a["ocr_text"] or "") for a in d["assets"])
    hits = (await client.get("/search", params={"q": "blue retention chart"})).json()["hits"]
    assert hits and hits[0]["item"]["id"] == item["id"]


async def test_failed_item_keeps_data_and_retries(client: AsyncClient) -> None:
    item = await save(client, url="http://127.0.0.1:9/unreachable", title="Saved anyway")
    for _ in range(4):
        await run_until_idle()
        from sqlalchemy import text as sql

        from smriti.db import get_sessionmaker

        async with get_sessionmaker()() as s:
            await s.execute(sql("UPDATE jobs SET run_after = now() WHERE status = 'queued'"))
            await s.commit()
    d = (await client.get(f"/items/{item['id']}")).json()
    assert d["status"] == "failed" and d["title"] == "Saved anyway" and "fetch" in d["error"]
    status = (await client.get("/admin/status")).json()
    assert status["failed"] and status["failed"][0]["step"] == "fetch"
    r = await client.post(f"/items/{item['id']}/retry")
    assert r.json()["status"] == "pending"


async def test_resurface_and_related(client: AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from smriti.db import get_sessionmaker
    from smriti.models import Item

    old = [
        await save(
            client,
            text="Vector search with HNSW graphs: recall versus latency tradeoffs in approximate nearest neighbour indexes",
            note="compare with ivfflat",
        ),
        await save(
            client, text="Sourdough starter feeding schedule and hydration ratios for a crusty loaf"
        ),
        await save(
            client,
            text="Product quantization compresses vectors for approximate nearest neighbour search at scale",
        ),
    ]
    await run_until_idle()
    async with get_sessionmaker()() as s:
        await s.execute(
            update(Item)
            .where(Item.id.in_([o["id"] for o in old]))
            .values(saved_at=datetime.now(UTC) - timedelta(days=200))
        )
        await s.commit()
    await save(
        client,
        text="Benchmarking approximate nearest neighbour vector search indexes for recall and latency",
    )
    await run_until_idle()

    home = (await client.get("/resurface", params={"surface": "home"})).json()["items"]
    assert home and len(home) <= 3
    assert all(p["reason"] for p in home)
    assert home[0]["item"]["id"] in {old[0]["id"], old[2]["id"]}

    detail = (await client.get(f"/items/{old[0]['id']}")).json()
    related = [r["item"]["id"] for r in detail["related"]]
    assert old[2]["id"] in related[:2] and old[1]["id"] not in related  # sourdough is unrelated

    r = await client.post("/events", json={"item_id": home[0]["item"]["id"], "kind": "dismiss"})
    assert r.status_code == 204


async def test_email_import_export(client: AsyncClient) -> None:
    r = await client.post(
        "/inbound/email/mailhook",
        json={
            "Subject": "Fwd: read this",
            "TextBody": "Great piece https://example.com/essay?utm_source=mail\nabout focus",
        },
    )
    assert r.json() == {"created": 1}
    assert (await client.post("/inbound/email/wrong", json={})).status_code == 404

    r = await client.post(
        "/import",
        files={"file": ("bookmarks.html", (FIXTURES / "bookmarks.html").read_bytes(), "text/html")},
    )
    body = r.json()
    assert body["format"] == "bookmarks-html" and body["found"] == 2 and body["created"] == 2
    again = (
        await client.post(
            "/import",
            files={
                "file": ("bookmarks.html", (FIXTURES / "bookmarks.html").read_bytes(), "text/html")
            },
        )
    ).json()
    assert again["created"] == 0 and again["skipped"] == 2

    grid = (await client.get("/items")).json()["items"]
    typo = next(i for i in grid if i["url"] == "https://example.com/typography")
    assert typo["note"] == "Read the chapter on line length"
    assert "design" in typo["tags"]
    assert typo["saved_at"].startswith("2022-04-15")

    export = await client.get("/export")
    with zipfile.ZipFile(io.BytesIO(export.content)) as z:
        lines = z.read("items.jsonl").decode().splitlines()
        assert len(lines) == 3


async def test_reindex_and_settings(client: AsyncClient) -> None:
    await save(client, text="A note about typography and line length")
    await run_until_idle()
    r = (await client.post("/admin/reindex", json={"step": "tags", "force": True})).json()
    assert r == {"step": "enrich.tags", "version": 1, "enqueued": 1}
    assert await run_until_idle() == 2  # the tag job, then a refresh of the search fields
    assert (
        await client.post("/admin/reindex", json={"step": "tags", "version": 9})
    ).status_code == 409
    r = await client.put(
        "/admin/settings/models/summary", json={"provider": "ollama", "model": "qwen2.5:3b"}
    )
    assert r.json()["summary"]["model"] == "qwen2.5:3b"
    models = (await client.get("/admin/settings/models")).json()
    assert models["overrides"]["summary"]["provider"] == "ollama"


@pytest.mark.parametrize("n", [1])
async def test_stream_reports_status(client: AsyncClient, n: int) -> None:
    from smriti.notify import broadcaster

    async with broadcaster.subscribe() as queue:
        await save(client, text="stream me")
        payload = json.loads(await asyncio.wait_for(queue.get(), 5))
        assert payload["status"] == "pending" and payload["step"] == "saved"
        await run_until_idle()
        steps = []
        while not queue.empty():
            steps.append(json.loads(queue.get_nowait())["step"])
        assert steps[-1] == "index"


async def test_backfill_cascades_to_enrichment(client: AsyncClient) -> None:
    from sqlalchemy import text as sql

    from smriti.db import get_sessionmaker

    item = await save(
        client, text="A short note about sourdough starters and their feeding schedules today."
    )
    await run_until_idle()
    async with get_sessionmaker()() as s:
        await s.execute(
            sql("UPDATE item_content SET text = :t WHERE item_id = :id"),
            {
                "t": "Completely different words about orbital mechanics and the rocket equation now.",
                "id": item["id"],
            },
        )
        await s.commit()
    r = (await client.post("/admin/reindex", json={"step": "extract", "force": True})).json()
    assert r["enqueued"] == 1
    # extract, snapshot, enrich, index all re-run under a fresh key suffix.
    assert await run_until_idle() == 4
    d = (await client.get(f"/items/{item['id']}")).json()
    assert "orbital" in d["summary"]
    hits = (await client.get("/search", params={"q": "rocket equation"})).json()["hits"]
    assert hits and hits[0]["item"]["id"] == item["id"]
