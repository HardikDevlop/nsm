"""Signed, device-bound Windows helper challenge service.

This module contains no routes and performs no database work at import time.
Callers own the transaction: challenge consumption is flushed in the caller's
transaction so evidence persistence can commit or roll back atomically with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any
from uuid import UUID, uuid4

from jose import JWTError, jwt
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.config.settings import get_settings
from backend.models import Device
from .models import WindowsHelperChallenge


ALGORITHM = "HS256"
TOKEN_TYPE = "windows-helper-challenge"
TOKEN_VERSION = 1
DEFAULT_PURPOSE = "windows_helper_evidence"
DEFAULT_TTL_SECONDS = 30
MAX_TTL_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 5


class ChallengeError(ValueError):
    """Safe caller-facing challenge validation failure."""


@dataclass(frozen=True)
class IssuedChallenge:
    token: str
    challenge_id: UUID
    device_id: int
    site_id: int
    collection_id: UUID
    purpose: str
    issued_at: datetime
    expires_at: datetime


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _settings():
    settings = get_settings()
    keys = settings.windows_helper_challenge_key_map
    active_id = settings.windows_helper_challenge_active_key_id.strip()
    if not keys or not active_id or active_id not in keys:
        raise ChallengeError("Windows helper challenge signing is disabled")
    return settings, keys, active_id


def _hash_nonce(nonce: str) -> str:
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()


def _timestamp(value: datetime) -> int:
    return int(_utc(value).timestamp())


def _claims(token: str, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise ChallengeError("Invalid helper challenge")
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise ChallengeError("Invalid helper challenge") from exc
    if header.get("alg") != ALGORITHM or header.get("typ") != TOKEN_TYPE:
        raise ChallengeError("Invalid helper challenge")
    key_id = header.get("kid")
    if not isinstance(key_id, str) or not key_id:
        raise ChallengeError("Invalid helper challenge")
    _, keys, _ = _settings()
    key = keys.get(key_id)
    if key is None:
        raise ChallengeError("Invalid helper challenge")
    try:
        payload = jwt.decode(token, key, algorithms=[ALGORITHM], options={"verify_exp": False, "verify_iat": False})
    except JWTError as exc:
        raise ChallengeError("Invalid helper challenge") from exc
    if payload.get("typ") != TOKEN_TYPE or payload.get("ver") != TOKEN_VERSION:
        raise ChallengeError("Invalid helper challenge")
    required = ("jti", "device_id", "site_id", "collection_id", "purpose", "iat", "exp", "nonce")
    if any(field not in payload for field in required):
        raise ChallengeError("Invalid helper challenge")
    if payload.get("purpose") != DEFAULT_PURPOSE:
        raise ChallengeError("Invalid helper challenge")
    try:
        challenge_id = UUID(str(payload["jti"]))
        collection_id = UUID(str(payload["collection_id"]))
        device_id = int(payload["device_id"])
        site_id = int(payload["site_id"])
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ChallengeError("Invalid helper challenge") from exc
    if device_id <= 0 or site_id <= 0 or not isinstance(payload["nonce"], str) or not payload["nonce"]:
        raise ChallengeError("Invalid helper challenge")
    current = _timestamp(_utc(now))
    if issued_at > current + MAX_CLOCK_SKEW_SECONDS or expires_at <= current or expires_at <= issued_at:
        raise ChallengeError("Invalid helper challenge")
    return {
        "challenge_id": challenge_id,
        "collection_id": collection_id,
        "device_id": device_id,
        "site_id": site_id,
        "purpose": payload["purpose"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": payload["nonce"],
    }


def _validate_binding(claims: dict[str, Any], *, device_id: int, site_id: int, collection_id: UUID, purpose: str) -> None:
    if claims["device_id"] != device_id or claims["site_id"] != site_id or claims["collection_id"] != collection_id or claims["purpose"] != purpose:
        raise ChallengeError("Invalid helper challenge")


def issue_challenge(
    db: Session,
    *,
    device_id: int,
    collection_id: UUID,
    purpose: str = DEFAULT_PURPOSE,
    site_id: int | None = None,
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> IssuedChallenge:
    """Issue and flush one challenge for an existing device collection."""
    _, keys, active_id = _settings()
    if purpose != DEFAULT_PURPOSE or not isinstance(collection_id, UUID):
        raise ChallengeError("Invalid helper challenge request")
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ChallengeError("Invalid helper challenge expiry")
    device = db.get(Device, device_id)
    if device is None or (site_id is not None and device.site_id != site_id):
        raise ChallengeError("Invalid helper challenge binding")
    bound_site_id = device.site_id
    issued_at = _utc(now)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    challenge_id = uuid4()
    # The challenge ID is the cryptographically random replay identifier. It
    # is also the deterministic nonce input for materialization; no raw nonce
    # needs to be persisted or recovered from a hash.
    nonce = str(challenge_id)
    row = WindowsHelperChallenge(
        challenge_id=challenge_id,
        device_id=device_id,
        site_id=bound_site_id,
        collection_id=collection_id,
        purpose=purpose,
        nonce_hash=_hash_nonce(nonce),
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    token = jwt.encode(
        {
            "typ": TOKEN_TYPE,
            "ver": TOKEN_VERSION,
            "jti": str(challenge_id),
            "device_id": device_id,
            "site_id": bound_site_id,
            "collection_id": str(collection_id),
            "purpose": purpose,
            "iat": _timestamp(issued_at),
            "exp": _timestamp(expires_at),
            "nonce": nonce,
        },
        keys[active_id],
        algorithm=ALGORITHM,
        headers={"kid": active_id, "typ": TOKEN_TYPE},
    )
    return IssuedChallenge(token, challenge_id, device_id, bound_site_id, collection_id, purpose, issued_at, expires_at)


def materialize_challenge(db: Session, challenge_id: UUID, *, now: datetime | None = None) -> IssuedChallenge:
    """Sign an existing active challenge from immutable persisted fields."""
    _, keys, active_id = _settings()
    current = _utc(now)
    row = db.query(WindowsHelperChallenge).filter(WindowsHelperChallenge.challenge_id == challenge_id).first()
    if row is None or row.consumed_at is not None or row.cancelled_at is not None or row.expires_at <= current:
        raise ChallengeError("Invalid helper challenge")
    if row.nonce_hash != _hash_nonce(str(row.challenge_id)):
        raise ChallengeError("Invalid helper challenge")
    token = jwt.encode(
        {"typ": TOKEN_TYPE, "ver": TOKEN_VERSION, "jti": str(row.challenge_id), "device_id": row.device_id,
         "site_id": row.site_id, "collection_id": str(row.collection_id), "purpose": row.purpose,
         "iat": _timestamp(row.issued_at), "exp": _timestamp(row.expires_at), "nonce": str(row.challenge_id)},
        keys[active_id], algorithm=ALGORITHM, headers={"kid": active_id, "typ": TOKEN_TYPE},
    )
    return IssuedChallenge(token, row.challenge_id, row.device_id, row.site_id, row.collection_id, row.purpose, row.issued_at, row.expires_at)


def verify_challenge(
    db: Session,
    token: str,
    *,
    device_id: int,
    site_id: int,
    collection_id: UUID,
    purpose: str = DEFAULT_PURPOSE,
    now: datetime | None = None,
) -> WindowsHelperChallenge:
    """Verify signature, claims, binding, nonce hash, and active database state."""
    claims = _claims(token, now=now)
    _validate_binding(claims, device_id=device_id, site_id=site_id, collection_id=collection_id, purpose=purpose)
    current = _utc(now)
    row = db.query(WindowsHelperChallenge).filter(WindowsHelperChallenge.challenge_id == claims["challenge_id"]).first()
    if row is None or row.device_id != device_id or row.site_id != site_id or row.collection_id != collection_id or row.purpose != purpose:
        raise ChallengeError("Invalid helper challenge")
    if row.consumed_at is not None or row.cancelled_at is not None or row.expires_at <= current:
        raise ChallengeError("Invalid helper challenge")
    if row.nonce_hash != _hash_nonce(claims["nonce"]):
        raise ChallengeError("Invalid helper challenge")
    if _timestamp(row.issued_at) != claims["issued_at"] or _timestamp(row.expires_at) != claims["expires_at"]:
        raise ChallengeError("Invalid helper challenge")
    return row


def consume_challenge(
    db: Session,
    token: str,
    *,
    device_id: int,
    site_id: int,
    collection_id: UUID,
    purpose: str = DEFAULT_PURPOSE,
    now: datetime | None = None,
) -> WindowsHelperChallenge:
    """Atomically consume a challenge; caller controls commit/rollback."""
    claims = _claims(token, now=now)
    _validate_binding(claims, device_id=device_id, site_id=site_id, collection_id=collection_id, purpose=purpose)
    current = _utc(now)
    statement = (
        update(WindowsHelperChallenge)
        .where(
            WindowsHelperChallenge.challenge_id == claims["challenge_id"],
            WindowsHelperChallenge.device_id == device_id,
            WindowsHelperChallenge.site_id == site_id,
            WindowsHelperChallenge.collection_id == collection_id,
            WindowsHelperChallenge.purpose == purpose,
            WindowsHelperChallenge.nonce_hash == _hash_nonce(claims["nonce"]),
            WindowsHelperChallenge.consumed_at.is_(None),
            WindowsHelperChallenge.cancelled_at.is_(None),
            WindowsHelperChallenge.expires_at > current,
        )
        .values(consumed_at=current)
        .returning(WindowsHelperChallenge)
    )
    row = db.execute(statement).first()
    if row is None:
        raise ChallengeError("Invalid helper challenge")
    return row[0] if isinstance(row, tuple) else row


def cancel_challenge(db: Session, challenge_id: UUID, *, now: datetime | None = None) -> bool:
    """Cancel an unused challenge without overwriting a consumed one."""
    current = _utc(now)
    statement = (
        update(WindowsHelperChallenge)
        .where(WindowsHelperChallenge.challenge_id == challenge_id, WindowsHelperChallenge.consumed_at.is_(None), WindowsHelperChallenge.cancelled_at.is_(None))
        .values(cancelled_at=current)
    )
    return db.execute(statement).rowcount == 1


def lookup_active_challenge(db: Session, *, device_id: int, collection_id: UUID, now: datetime | None = None) -> WindowsHelperChallenge | None:
    """Return the active challenge row for a device collection, if any."""
    current = _utc(now)
    return (
        db.query(WindowsHelperChallenge)
        .filter(
            WindowsHelperChallenge.device_id == device_id,
            WindowsHelperChallenge.collection_id == collection_id,
            WindowsHelperChallenge.consumed_at.is_(None),
            WindowsHelperChallenge.cancelled_at.is_(None),
            WindowsHelperChallenge.expires_at > current,
        )
        .first()
    )
