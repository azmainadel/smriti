"""Blob storage for originals, snapshots and assets. A directory by default, any S3-compatible store optionally."""

import asyncio
import hashlib
import hmac
import mimetypes
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from smriti.config import get_settings

# Slim container images ship without /etc/mime.types; register what Smriti stores.
for _type, _ext in (
    ("image/webp", ".webp"),
    ("image/avif", ".avif"),
    ("text/html", ".html"),
    ("application/pdf", ".pdf"),
    ("audio/mpeg", ".mp3"),
    ("audio/mp4", ".m4a"),
):
    mimetypes.add_type(_type, _ext)


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete_prefix(self, prefix: str) -> None: ...
    def iter_keys(self, prefix: str) -> AsyncIterator[str]: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"invalid key: {key}")
        return path

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete_prefix(self, prefix: str) -> None:
        def _rm() -> None:
            base = self._path(prefix)
            if base.is_file():
                base.unlink()
                return
            for p in sorted(base.rglob("*"), reverse=True) if base.exists() else []:
                p.unlink() if p.is_file() else p.rmdir()
            if base.exists():
                base.rmdir()

        await asyncio.to_thread(_rm)

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        base = self._path(prefix)
        paths = await asyncio.to_thread(lambda: [p for p in base.rglob("*") if p.is_file()])
        for p in paths:
            yield p.relative_to(self.root).as_posix()


class S3Storage:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
        )

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type or guess_type(key),
        )

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)

    async def delete_prefix(self, prefix: str) -> None:
        keys = [k async for k in self.iter_keys(prefix)]
        for i in range(0, len(keys), 1000):
            batch = {"Objects": [{"Key": k} for k in keys[i : i + 1000]]}
            await asyncio.to_thread(self.client.delete_objects, Bucket=self.bucket, Delete=batch)

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        pages = await asyncio.to_thread(
            lambda: list(paginator.paginate(Bucket=self.bucket, Prefix=prefix))
        )
        for page in pages:
            for obj in page.get("Contents", []):
                yield obj["Key"]


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    return S3Storage() if s.storage_backend == "s3" else LocalStorage(s.storage_dir)


def guess_type(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


def item_prefix(item_id: object) -> str:
    return f"items/{item_id}/"


def _signature(key: str, expires: int) -> str:
    secret = get_settings().signing_key.encode()
    return hmac.new(secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(key: str | None, ttl_s: int = 6 * 3600) -> str | None:
    """A URL for <img src> and downloads. Expiry is rounded so URLs stay cacheable for an hour."""
    if not key:
        return None
    expires = (int(time.time()) // 3600 + 1) * 3600 + ttl_s
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/files/{quote(key)}?exp={expires}&sig={_signature(key, expires)}"


def verify_signature(key: str, expires: int, sig: str) -> bool:
    return expires > time.time() and hmac.compare_digest(sig, _signature(key, expires))
