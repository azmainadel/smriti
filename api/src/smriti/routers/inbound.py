"""Forward anything to a private address. Works with any inbound-mail webhook (Postmark,
Mailgun, SendGrid, Cloudflare Email Workers) or a plain JSON body; the secret is in the path."""

import base64
import hmac
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from smriti import items as item_service
from smriti.config import get_settings
from smriti.db import get_session
from smriti.pipeline.extractors.html import html_to_text
from smriti.schemas import ItemCreate
from smriti.urls import find_urls

router = APIRouter(tags=["capture"])
MAX_URLS = 5
_SIGNATURE = re.compile(r"\n--\s*\n.*$", re.S)
_QUOTED = re.compile(r"^>.*$", re.M)


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Map provider field names onto {subject, text, html, attachments[{name, type, data}]}."""
    lower = {k.lower(): v for k, v in payload.items()}
    attachments = []
    for a in lower.get("attachments") or []:
        content = a.get("content") or a.get("Content") or ""
        attachments.append(
            {
                "name": a.get("filename") or a.get("name") or a.get("Name") or "attachment",
                "type": a.get("content_type")
                or a.get("contenttype")
                or a.get("ContentType")
                or a.get("type"),
                "data": base64.b64decode(content) if isinstance(content, str) else content,
            }
        )
    return {
        "subject": lower.get("subject") or "",
        "text": lower.get("stripped-text")
        or lower.get("textbody")
        or lower.get("body-plain")
        or lower.get("text")
        or "",
        "html": lower.get("htmlbody") or lower.get("body-html") or lower.get("html") or "",
        "attachments": attachments,
    }


def plan(mail: dict[str, Any]) -> list[ItemCreate]:
    """URLs in the body become link items, the rest of the body their note. A body with no
    URL becomes a note titled by the subject."""
    body = mail["text"] or (html_to_text(mail["html"]) if mail["html"] else "")
    body = _QUOTED.sub("", _SIGNATURE.sub("", body)).strip()
    subject = re.sub(r"^(fwd?|re):\s*", "", mail["subject"].strip(), flags=re.I)
    urls = list(dict.fromkeys(find_urls(body) or find_urls(subject)))[:MAX_URLS]
    if urls:
        rest = body
        for u in urls:
            rest = rest.replace(u, "")
        note = re.sub(r"\n{3,}", "\n\n", rest).strip() or None
        return [ItemCreate(url=u, note=note, capture="email") for u in urls]
    if body:
        return [ItemCreate(text=body, title=subject or None, capture="email")]
    return []


@router.post("/inbound/email/{secret}", status_code=status.HTTP_202_ACCEPTED)
async def inbound_email(
    secret: str, request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, int]:
    expected = get_settings().inbound_email_secret
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        payload: dict[str, Any] = {k: v for k, v in form.items() if isinstance(v, str)}
        payload["attachments"] = [
            {"filename": v.filename, "content_type": v.content_type, "content": await v.read()}
            for k, v in form.multi_items()
            if not isinstance(v, str) and k.startswith("attachment")
        ]
    else:
        payload = await request.json()
    mail = normalize(payload)
    created = 0
    for data in plan(mail):
        await item_service.save(session, data)
        created += 1
    for a in mail["attachments"]:
        if a["data"]:
            await item_service.save_file(
                session,
                a["name"],
                a["data"],
                a["type"],
                capture="email",
                note=mail["subject"] or None,
            )
            created += 1
    await session.commit()
    return {"created": created}
