"""`smriti`: save from the terminal, bulk import, and run the server-side pieces.

Client commands (save, import, search, export) talk to the API like any other device.
Server commands (serve, work, migrate, eval, bench) run against the database directly.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import httpx
import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)
CONFIG = Path(os.environ.get("SMRITI_CONFIG", Path.home() / ".config" / "smriti" / "cli.json"))


def _config() -> dict[str, str]:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    return {}


def _client() -> httpx.Client:
    cfg = _config()
    url = os.environ.get("SMRITI_API_URL") or cfg.get("url")
    token = os.environ.get("SMRITI_TOKEN") or cfg.get("token")
    if not url or not token:
        typer.echo("Not logged in. Run: smriti login --url http://localhost:8000", err=True)
        raise typer.Exit(1)
    return httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120)


def _check(r: httpx.Response) -> dict:
    if r.is_error:
        typer.echo(f"{r.status_code}: {r.text}", err=True)
        raise typer.Exit(1)
    return r.json() if r.content else {}


@app.command()
def login(
    url: Annotated[str, typer.Option(help="API base URL")] = "http://localhost:8000",
    name: Annotated[str, typer.Option(help="Device name for this token")] = "cli",
) -> None:
    """Exchange the owner secret for a CLI token."""
    secret = typer.prompt("Owner secret", hide_input=True)
    r = httpx.post(f"{url}/auth/tokens", json={"name": name, "secret": secret}, timeout=30)
    body = _check(r)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"url": url, "token": body["token"]}))
    CONFIG.chmod(0o600)
    typer.echo(f"Logged in. Token saved to {CONFIG}")


@app.command()
def save(
    what: Annotated[str, typer.Argument(help="A URL, some text, a file path, or - for stdin")],
    note: Annotated[str | None, typer.Option("--note", "-n")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t")] = None,
) -> None:
    """Save a URL, a note, or a file."""
    with _client() as c:
        if what == "-":
            what = sys.stdin.read()
        path = Path(what)
        if len(what) < 4096 and path.is_file():
            with path.open("rb") as f:
                body = _check(
                    c.post(
                        "/items",
                        files={"file": (path.name, f)},
                        data={"note": note or "", "capture": "cli"},
                    )
                )
        else:
            key = (
                "url"
                if what.strip().startswith(("http://", "https://")) and " " not in what.strip()
                else "text"
            )
            body = _check(
                c.post(
                    "/items",
                    json={key: what.strip(), "note": note, "tags": tag or [], "capture": "cli"},
                )
            )
    typer.echo(f"{body['id']}  {body['type']}  {body.get('title') or body.get('url') or ''}")


@app.command("import")
def import_(file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Import browser bookmarks (HTML), a Pocket export or a Raindrop CSV."""
    with _client() as c, file.open("rb") as f:
        body = _check(c.post("/import", files={"file": (file.name, f)}))
    typer.echo(
        f"{body['format']}: {body['created']} saved, {body['skipped']} already there ({body['found']} found)"
    )


@app.command()
def search(query: Annotated[list[str], typer.Argument()], limit: int = 10) -> None:
    """Search from the terminal."""
    with _client() as c:
        body = _check(c.get("/search", params={"q": " ".join(query), "limit": limit}))
    if body["chips"]:
        typer.echo("filters: " + ", ".join(f"{ch['kind']}={ch['label']}" for ch in body["chips"]))
    for hit in body["hits"]:
        item = hit["item"]
        typer.echo(f"{item['type']:<8} {item.get('title') or item.get('url') or item['id']}")
        if item.get("url"):
            typer.echo(f"         {item['url']}")
    typer.echo(f"({len(body['hits'])} results in {body['took_ms']} ms)", err=True)


@app.command()
def export(out: Annotated[Path, typer.Option("--out", "-o")] = Path("smriti-export.zip")) -> None:
    """Download everything: JSON plus all files."""
    with _client() as c, c.stream("GET", "/export") as r, out.open("wb") as f:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            f.write(chunk)
    typer.echo(f"Wrote {out}")


@app.command()
def reindex(step: str, force: bool = False) -> None:
    """Re-run one step at its current version across all items."""
    with _client() as c:
        body = _check(c.post("/admin/reindex", json={"step": step, "force": force}))
    typer.echo(f"{body['step']} v{body['version']}: {body['enqueued']} jobs queued")


# ---------- server side ----------


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    """Run the API."""
    import uvicorn

    uvicorn.run("smriti.main:app", host=host, port=port, reload=reload, proxy_headers=True)


@app.command()
def work(once: Annotated[bool, typer.Option(help="Drain the queue and exit")] = False) -> None:
    """Run the workflow runner."""
    from smriti.logs import setup_logging
    from smriti.worker import main, run_until_idle

    if once:
        setup_logging()
        typer.echo(f"processed {asyncio.run(run_until_idle())} jobs")
    else:
        main()


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(cfg, "head")


@app.command("eval")
def eval_(
    dataset: Annotated[
        Path, typer.Option(help="Directory with corpus.jsonl and queries.jsonl")
    ] = Path("evals/seed"),
    load: Annotated[bool, typer.Option(help="Load the corpus first (wipes the database!)")] = False,
    min_recall: float = 0.0,
    min_mrr: float = 0.0,
    out: Path | None = None,
) -> None:
    """Search quality: recall@10 and MRR on a fixed query set."""
    from smriti.evaluation import run_eval

    report = asyncio.run(run_eval(dataset, load=load))
    typer.echo(json.dumps(report["summary"], indent=2))
    if out:
        out.write_text(json.dumps(report, indent=2, default=str))
    if report["summary"]["recall@10"] < min_recall or report["summary"]["mrr"] < min_mrr:
        typer.echo("below threshold", err=True)
        raise typer.Exit(1)


@app.command()
def bench(
    items: int = 10_000,
    queries: int = 200,
    seed_db: Annotated[
        bool, typer.Option(help="Insert synthetic items first (wipes the database!)")
    ] = False,
) -> None:
    """Search latency: p50/p95 over synthetic queries."""
    from smriti.evaluation import run_bench

    typer.echo(json.dumps(asyncio.run(run_bench(items, queries, seed_db)), indent=2))


if __name__ == "__main__":
    app()
