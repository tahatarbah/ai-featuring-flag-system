from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from aiflag.config import settings
from aiflag.db import get_db
from aiflag.models import SdkKey


def hash_sdk_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_admin(authorization: Annotated[str | None, Header()] = None) -> str:
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return "admin"


def require_sdk(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> SdkKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing SDK key")
    token = authorization.removeprefix("Bearer ").strip()
    row = db.query(SdkKey).filter(SdkKey.key_hash == hash_sdk_key(token)).first()
    if row is None or row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid SDK key")
    return row
