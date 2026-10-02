from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config.settings import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, jti: str | None = None) -> str:
    settings = get_settings()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    claims = {"sub": subject, "exp": expires_at}
    if jti:
        claims["jti"] = jti
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def decode_access_token_claims(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
