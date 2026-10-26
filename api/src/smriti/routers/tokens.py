import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.auth import Authed, check_owner_secret, hash_token, new_token
from smriti.db import get_session
from smriti.models import ApiToken
from smriti.schemas import TokenCreate, TokenCreated, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _out(t: ApiToken) -> TokenOut:
    return TokenOut(
        id=t.id,
        name=t.name,
        created_at=t.created_at,
        last_used_at=t.last_used_at,
        revoked_at=t.revoked_at,
    )


@router.post("/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenCreate, session: Session) -> TokenCreated:
    """Exchange the owner secret for a token for one device. The token is shown once."""
    check_owner_secret(body.secret)
    raw = new_token()
    row = ApiToken(name=body.name, token_hash=hash_token(raw))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return TokenCreated(**_out(row).model_dump(), token=raw)


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(session: Session, _: Authed) -> list[TokenOut]:
    rows = await session.execute(select(ApiToken).order_by(ApiToken.created_at.desc()))
    return [_out(t) for t in rows.scalars()]


@router.get("/me", response_model=TokenOut)
async def me(token: Authed) -> TokenOut:
    return _out(token)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, session: Session, _: Authed) -> None:
    row = await session.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such token")
    row.revoked_at = datetime.now(UTC)
    await session.commit()
