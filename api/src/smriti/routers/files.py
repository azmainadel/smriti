from fastapi import APIRouter, HTTPException, Response, status

from smriti.storage import get_storage, guess_type, verify_signature

router = APIRouter(tags=["files"])


@router.get("/files/{key:path}", include_in_schema=False)
async def get_file(key: str, exp: int, sig: str) -> Response:
    """Serve a stored file behind a signed, expiring URL, so <img> tags need no auth header."""
    if not verify_signature(key, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad or expired signature")
    try:
        data = await get_storage().get(key)
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such file") from e
    except Exception as e:  # S3 raises its own NoSuchKey
        if "NoSuchKey" in type(e).__name__ or "NoSuchKey" in str(e):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such file") from e
        raise
    headers = {"Cache-Control": "private, max-age=3600"}
    media_type = guess_type(key)
    if key.endswith("archive.html"):
        # Archived pages are untrusted HTML: sandbox them.
        headers["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline' data:"
        )
    return Response(data, media_type=media_type, headers=headers)
