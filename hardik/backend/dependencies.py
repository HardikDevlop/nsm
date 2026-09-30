from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, selectinload

from backend.auth.security import decode_access_token
from backend.database.session import get_db
from backend.models import Role, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = decode_access_token(credentials.credentials)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = (
        db.query(User)
        .options(selectinload(User.role).selectinload(Role.permissions))
        .filter(User.email == email)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")
    return user


def get_user_permission_codes(user: User) -> set[str]:
    if user.role is None:
        return set()
    return {permission.code for permission in user.role.permissions}


def require_permission(code: str):
    """RBAC dependency factory: allows the request only when the current
    user's role owns the permission code. Role names never grant implicit access."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if code not in get_user_permission_codes(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {code}",
            )
        return current_user

    return checker


def require_any_permission(*codes: str):
    """Allow a read endpoint when the user has any relevant permission."""
    def checker(current_user: User = Depends(get_current_user)) -> User:
        granted = get_user_permission_codes(current_user)
        if not granted.intersection(codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing one of permissions: {', '.join(codes)}",
            )
        return current_user
    return checker
