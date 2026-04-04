"""Reference URL shortener — satisfies challenges/library/url-shortener-saas hidden_tests.

Run from this directory: uvicorn main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="URL Shortener Golden")

_lock = asyncio.Lock()
# code -> {url, expires_at (monotonic or None), clicks}
_store: dict[str, dict[str, Any]] = {}


def _valid_public_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


class ShortenIn(BaseModel):
    url: str = Field(min_length=1)
    custom_alias: str | None = None
    expires_in_seconds: int | None = Field(default=None, ge=1)

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not _valid_public_url(v):
            raise ValueError("invalid url")
        return v


def _new_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "x")[:8]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/shorten")
async def shorten(body: ShortenIn) -> JSONResponse:
    async with _lock:
        code: str
        if body.custom_alias:
            if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", body.custom_alias):
                raise HTTPException(status_code=422, detail="invalid alias")
            if body.custom_alias in _store:
                raise HTTPException(status_code=409, detail="alias taken")
            code = body.custom_alias
        else:
            for _ in range(20):
                c = _new_code()
                if c not in _store:
                    code = c
                    break
            else:
                raise HTTPException(status_code=500, detail="could not allocate code")

        exp: float | None = None
        if body.expires_in_seconds is not None:
            exp = time.monotonic() + float(body.expires_in_seconds)

        _store[code] = {
            "url": body.url,
            "expires_at": exp,
            "clicks": 0,
        }
    return JSONResponse(
        status_code=201,
        content={"short_code": code, "code": code},
    )


@app.get("/urls")
async def list_urls() -> list[dict[str, Any]]:
    async with _lock:
        return [
            {"short_code": c, "url": rec["url"], "clicks": rec["clicks"]}
            for c, rec in _store.items()
        ]


@app.get("/{code}")
async def redirect_or_404(code: str) -> Response:
    if code in ("health", "shorten", "urls", "links", "favicon.ico"):
        raise HTTPException(status_code=404)
    async with _lock:
        rec = _store.get(code)
        if rec is None:
            raise HTTPException(status_code=404)
        exp = rec.get("expires_at")
        if exp is not None and time.monotonic() > exp:
            raise HTTPException(status_code=410)
        rec["clicks"] = rec["clicks"] + 1
        target = rec["url"]
    return RedirectResponse(url=target, status_code=301)


@app.delete("/{code}")
async def delete_url(code: str) -> Response:
    async with _lock:
        if code not in _store:
            raise HTTPException(status_code=404)
        del _store[code]
    return Response(status_code=204)


@app.get("/analytics/{code}")
async def analytics(code: str) -> dict[str, Any]:
    async with _lock:
        rec = _store.get(code)
        if rec is None:
            raise HTTPException(status_code=404)
        return {
            "clicks": rec["clicks"],
            "click_count": rec["clicks"],
            "url": rec["url"],
            "original_url": rec["url"],
        }
