"""Device-bound authentication primitives for the Windows interactive helper."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

TOKEN_BYTES = 32

def issue_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token[:12], hashlib.sha256(token.encode()).hexdigest()

def matches_token(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), stored_hash)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
