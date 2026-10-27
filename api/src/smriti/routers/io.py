from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.auth import Authed
from smriti.db import get_session
from smriti.export import build_export
from smriti.importers import import_bookmarks, parse_any
from smriti.schemas import ImportOut

router = APIRouter(tags=["import-export"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/import", response_model=ImportOut)
async def import_file(file: UploadFile, session: Session, _: Authed) -> ImportOut:
    """Browser bookmarks HTML, Pocket export (HTML or CSV) or Raindrop CSV."""
    try:
        fmt, bookmarks = parse_any(file.filename or "", await file.read())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    created, skipped = await import_bookmarks(session, bookmarks)
    return ImportOut(format=fmt, found=len(bookmarks), created=created, skipped=skipped)


@router.get("/export", response_class=FileResponse)
async def export(session: Session, _: Authed, background: BackgroundTasks) -> FileResponse:
    path = await build_export(session)
    background.add_task(path.unlink, missing_ok=True)
    return FileResponse(path, media_type="application/zip", filename="smriti-export.zip")
