from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from smriti import __version__
from smriti.config import get_settings
from smriti.db import get_engine
from smriti.logs import setup_logging
from smriti.notify import broadcaster
from smriti.routers import (
    admin,
    events,
    files,
    inbound,
    io,
    items,
    resurface,
    search,
    stream,
    tokens,
)
from smriti.schemas import ItemCreate
from smriti.telemetry import setup_tracing


@asynccontextmanager
async def lifespan(_: FastAPI):  # noqa: ANN201
    yield
    await broadcaster.close()
    await get_engine().dispose()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Smriti",
        version=__version__,
        summary="Save anything, find it by meaning.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # Browser extensions call from their own origins.
        allow_origin_regex=r"^(chrome|moz)-extension://.*$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (items, search, resurface, events, stream, admin, tokens, files, inbound, io):
        app.include_router(module.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    def openapi() -> dict:
        # POST /items reads its body by hand (JSON or multipart), so register its JSON model.
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, summary=app.summary, routes=app.routes
            )
            body = ItemCreate.model_json_schema(ref_template="#/components/schemas/{model}")
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            components.update(body.pop("$defs", {}))
            components["ItemCreate"] = body
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    setup_tracing("smriti-api", app)
    return app


app = create_app()
