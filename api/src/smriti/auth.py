"""Single owner, per-device API tokens. The owner secret only ever mints tokens."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.config import get_settings
from smriti.db import get_session
from smriti.models import ApiToken

TOKEN_PREFIX = "smr_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def check_owner_secret(secret: str) -> None:
    if not hmac.compare_digest(secret.encode(), get_settings().owner_secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong owner secret")


async def require_token(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    token: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> ApiToken:
    """Bearer token from the Authorization header, or ?token= for EventSource, which cannot
    send headers."""
    header = request.headers.get("authorization", "")
    raw = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    row = (
        await session.execute(
            select(ApiToken).where(
                ApiToken.token_hash == hash_token(raw), ApiToken.revoked_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked token")
    now = datetime.now(UTC)
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=5):
        await session.execute(
            update(ApiToken).where(ApiToken.id == row.id).values(last_used_at=now)
        )
        await session.commit()
    return row


Authed = Annotated[ApiToken, Depends(require_token)]
