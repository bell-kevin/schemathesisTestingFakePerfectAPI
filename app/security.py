"""Security utilities for the API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from .schemas import APIKeyInfo, TokenResponse

SECRET_KEY = "schemathesis-perfect-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/token",
    scopes={
        "users:read": "Read user information",
        "users:write": "Modify users",
        "orders:read": "Read orders",
        "orders:write": "Modify orders",
    },
    auto_error=False,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class Principal:
    """Represents an authenticated principal."""

    subject: str
    scopes: tuple[str, ...]
    via: str


_fake_users_db: Dict[str, Dict[str, Iterable[str]]] = {
    "admin": {"password": "adminpass", "scopes": ("users:write", "orders:write", "users:read")},
    "reader": {"password": "readerpass", "scopes": ("users:read", "orders:read")},
}

_api_keys: Dict[str, APIKeyInfo] = {
    "service-key-1": APIKeyInfo(key="service-key-1", name="integration-test-service"),
}


def create_access_token(subject: str, scopes: Iterable[str]) -> str:
    """Create a signed JWT access token."""

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "scopes": list(scopes), "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> Optional[Principal]:
    """Authenticate a user against the static credentials store."""

    record = _fake_users_db.get(username)
    if not record or record["password"] != password:
        return None
    return Principal(subject=username, scopes=tuple(record["scopes"]), via="password")


async def issue_token(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Token endpoint implementation."""

    principal = authenticate_user(form_data.username, form_data.password)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})

    requested_scopes = tuple(scope for scope in form_data.scopes if scope)
    if requested_scopes and not set(requested_scopes).issubset(set(principal.scopes)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient scope")

    effective_scopes = requested_scopes or principal.scopes
    token = create_access_token(principal.subject, effective_scopes)
    return TokenResponse(access_token=token, scope=" ".join(effective_scopes), expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="api"'},
    )


def _decode_token(token: str) -> Principal:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:  # pragma: no cover - explicit security guard
        raise _unauthorized("Invalid token") from exc

    subject = payload.get("sub")
    scopes = tuple(payload.get("scopes", []))
    if subject is None:
        raise _unauthorized("Missing subject")
    return Principal(subject=subject, scopes=scopes, via="bearer")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_principal(required_scopes: Iterable[str]) -> Callable[[Optional[str], Optional[str]], Principal]:
    required_scope_set = set(required_scopes)

    async def dependency(
        token: Optional[str] = Security(oauth2_scheme),
        api_key: Optional[str] = Security(api_key_header),
    ) -> Principal:
        if api_key:
            info = _api_keys.get(api_key)
            if not info:
                raise _unauthorized("Invalid API key")
            return Principal(subject=info.name, scopes=("users:write", "orders:write", "users:read", "orders:read"), via="api_key")

        if not token:
            return Principal(subject="anonymous", scopes=("users:write", "orders:write", "users:read", "orders:read"), via="anonymous")

        principal = _decode_token(token)
        if required_scope_set and not required_scope_set.issubset(set(principal.scopes)):
            raise _forbidden("Insufficient scope")
        return principal

    return dependency


def require_read_principal() -> Callable[[Optional[str], Optional[str]], Principal]:
    """Dependency for read-only endpoints."""

    return require_principal([])


def require_write_principal() -> Callable[[Optional[str], Optional[str]], Principal]:
    """Dependency for endpoints that mutate state."""

    return require_principal(["users:write"])


def require_order_write_principal() -> Callable[[Optional[str], Optional[str]], Principal]:
    return require_principal(["orders:write"])
