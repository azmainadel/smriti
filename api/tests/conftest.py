import os
import tempfile

# Settings are cached on first import, so the test environment is set before anything loads.
os.environ.update(
    {
        "SMRITI_DATABASE_URL": os.environ.get(
            "SMRITI_TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/smriti_test",
        ),
        "SMRITI_STORAGE_BACKEND": "local",
        "SMRITI_STORAGE_DIR": tempfile.mkdtemp(prefix="smriti-test-"),
        "SMRITI_EMBED_PROVIDER": "hash",
        "SMRITI_EMBED_DIM": "384",
        "SMRITI_LLM_PROVIDER": "none",
        "SMRITI_VISION_ENABLED": "false",
        "SMRITI_OWNER_SECRET": "test-secret",
        "SMRITI_INBOUND_EMAIL_SECRET": "mailhook",
        "SMRITI_LOG_JSON": "false",
        "SMRITI_LOG_LEVEL": "WARNING",
        # Hash embeddings score lower than real models; scale the related-items floor down.
        "SMRITI_RELATED_MIN_SIMILARITY": "0.15",
    }
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from smriti.db import get_engine  # noqa: E402

TABLES = "items, tags, entities, events, jobs, model_cache, api_tokens, app_settings"


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_db(request: pytest.FixtureRequest):
    if "db" not in request.keywords:
        yield
        return
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client():
    from smriti.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/tokens", json={"name": "tests", "secret": "test-secret"})
        assert r.status_code == 201, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "client" in getattr(item, "fixturenames", ()) or "session" in getattr(
            item, "fixturenames", ()
        ):
            item.add_marker("db")


@pytest.fixture
async def session():
    from smriti.db import get_sessionmaker

    async with get_sessionmaker()() as s:
        yield s
