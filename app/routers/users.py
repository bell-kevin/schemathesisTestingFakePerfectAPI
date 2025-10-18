"""User API endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..db import get_session
from ..models import AuditLog, Order, User
from ..schemas import (
    AuditLogEntry,
    OrderCollection,
    OrderRead,
    PaginationLinks,
    ProblemDetail,
    UserCollection,
    UserCreate,
    UserDetail,
    UserPatch,
    UserRead,
)
from ..security import Principal, require_write_principal

router = APIRouter(prefix="/users", tags=["Users"])

PROBLEM_CONTENT = {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}}
UNAUTHORIZED_RESPONSE = {
    "description": "Authentication required.",
    "content": PROBLEM_CONTENT,
    "headers": {"WWW-Authenticate": {"schema": {"type": "string"}}},
}
FORBIDDEN_RESPONSE = {
    "description": "Insufficient privileges.",
    "content": PROBLEM_CONTENT,
}


def _compute_etag(payload: object) -> str:
    """Create an ETag for the given payload."""

    encoded = json.dumps(jsonable_encoder(payload, by_alias=True), sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f'W/"{digest}"'


def _json_response(payload: object, *, status_code: int = 200, headers: Optional[dict[str, str]] = None) -> Response:
    return Response(
        status_code=status_code,
        content=json.dumps(jsonable_encoder(payload), ensure_ascii=False, separators=(",", ":")),
        media_type="application/json; charset=utf-8",
        headers=headers,
    )


@router.get(
    "",
    response_model=UserCollection,
    summary="List users",
    description="List users with optional filtering, sorting, and pagination.",
    operation_id="listUsers",
    responses={
        200: {
            "description": "Paginated list of users.",
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
                "X-Total-Count": {"schema": {"type": "integer"}},
                "Link": {"schema": {"type": "string"}},
            },
            "content": {
                "application/json; charset=utf-8": {
                    "example": {
                        "items": [],
                        "count": 0,
                        "links": {"self": "/users", "next": None, "prev": None},
                    }
                }
            },
        }
    },
)
async def list_users(
    request: Request,
    session: Session = Depends(get_session),
    q: Optional[str] = Query(default=None, description="Filter by name or email"),
    sort: str = Query(default="name", pattern=r"^-?name$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Response:
    """Return a paginated list of users."""

    filters = []
    if q:
        pattern = f"%{q.lower()}%"
        filters.append(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))

    sort_options = {
        "name": User.full_name.asc(),
        "-name": User.full_name.desc(),
    }
    order_by = sort_options.get(sort, User.full_name.asc())

    query = select(User)
    if filters:
        query = query.where(*filters)
    query = query.order_by(order_by, User.id)

    paged = session.exec(query.offset(offset).limit(limit)).all()

    count_stmt = select(func.count()).select_from(User)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(session.exec(count_stmt).one())

    collection = UserCollection(
        items=[UserRead.model_validate(user) for user in paged],
        count=total,
        links=PaginationLinks(self=str(request.url), next=None, prev=None),
    )

    next_offset = offset + limit
    prev_offset = max(offset - limit, 0)
    links_header = [f"<{str(request.url)}>; rel=\"self\""]

    if next_offset < total:
        next_url = str(request.url.include_query_params(offset=next_offset, limit=limit))
        collection.links.next = next_url
        links_header.append(f"<{next_url}>; rel=\"next\"")
    if offset > 0:
        prev_url = str(request.url.include_query_params(offset=prev_offset, limit=limit))
        collection.links.prev = prev_url
        links_header.append(f"<{prev_url}>; rel=\"prev\"")

    etag = _compute_etag(collection)
    headers = {
        "ETag": etag,
        "Cache-Control": "no-cache",
        "X-Total-Count": str(total),
        "Link": ", ".join(links_header),
    }
    return _json_response(collection, headers=headers)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    operation_id="createUser",
    responses={
        201: {
            "description": "User created successfully.",
            "headers": {
                "Location": {"schema": {"type": "string", "format": "uri"}},
                "ETag": {"schema": {"type": "string"}},
            },
        },
        409: {
            "description": "User already exists.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def create_user(
    request: Request,
    user_in: UserCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_write_principal()),
) -> Response:
    """Create a new user."""

    existing = session.exec(select(User).where(User.email == user_in.email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with email already exists")

    user = User(email=user_in.email, full_name=user_in.full_name, is_active=user_in.is_active)
    session.add(user)
    session.commit()
    session.refresh(user)

    body = UserRead.model_validate(user)
    etag = _compute_etag(body)
    location = str(request.url_for("getUser", user_id=user.id))
    headers = {
        "Location": location,
        "ETag": etag,
        "Cache-Control": "no-cache",
    }
    return _json_response(body, status_code=status.HTTP_201_CREATED, headers=headers)


@router.get(
    "/{user_id}",
    response_model=UserDetail,
    summary="Retrieve user",
    operation_id="getUser",
    responses={
        200: {
            "description": "User details.",
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}},
        },
        304: {
            "description": "Not modified.",
            "headers": {"ETag": {"schema": {"type": "string"}}},
        },
        404: {
            "description": "User not found.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
    },
)
async def get_user(
    user_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
) -> Response:
    """Retrieve a single user by identifier."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    audit_logs = session.exec(
        select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.performed_at.desc())
    ).all()

    detail = UserDetail.model_validate(user)
    detail = detail.model_copy(
        update={
            "audit_logs": [AuditLogEntry.model_validate(entry) for entry in audit_logs],
        }
    )

    content = jsonable_encoder(detail)
    etag = _compute_etag(content)

    if if_none_match:
        candidates = {candidate.strip() for candidate in if_none_match.split(",")}
        if etag in candidates:
            return Response(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={"ETag": etag, "Cache-Control": "no-cache"},
            )

    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(content, headers=headers)


@router.put(
    "/{user_id}",
    response_model=UserRead,
    summary="Replace user",
    operation_id="replaceUser",
    responses={
        200: {
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}
        },
        409: {
            "description": "User already exists.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def replace_user(
    user_id: UUID,
    user_in: UserCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_write_principal()),
) -> Response:
    """Replace a user resource."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.email != user_in.email:
        conflict = session.exec(select(User).where(User.email == user_in.email, User.id != user_id)).first()
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with email already exists")

    user.email = user_in.email
    user.full_name = user_in.full_name
    user.is_active = user_in.is_active
    user.updated_at = datetime.now(timezone.utc)

    session.add(user)
    session.commit()
    session.refresh(user)

    body = UserRead.model_validate(user)
    etag = _compute_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(body, headers=headers)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update user",
    operation_id="updateUser",
    responses={
        200: {
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}
        },
        409: {
            "description": "Conflict updating user.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def update_user(
    user_id: UUID,
    user_in: UserPatch,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_write_principal()),
) -> Response:
    """Patch a user resource."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_in.email is not None:
        conflict = session.exec(select(User).where(User.email == user_in.email, User.id != user_id)).first()
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with email already exists")
        user.email = user_in.email
    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    user.updated_at = datetime.now(timezone.utc)

    session.add(user)
    session.commit()
    session.refresh(user)

    body = UserRead.model_validate(user)
    etag = _compute_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(body, headers=headers)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    operation_id="deleteUser",
    responses={
        204: {"description": "User deleted."},
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def delete_user(
    user_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_write_principal()),
) -> Response:
    """Delete a user."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    session.delete(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{user_id}/orders",
    response_model=OrderCollection,
    summary="List a user's orders",
    operation_id="listUserOrders",
    responses={
        200: {
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
                "X-Total-Count": {"schema": {"type": "integer"}},
                "Link": {"schema": {"type": "string"}},
            }
        },
        404: {
            "description": "User not found.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
    },
)
async def list_user_orders(
    request: Request,
    user_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Response:
    """List orders for a single user."""

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    order_query = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.placed_at.desc(), Order.id)
        .offset(offset)
        .limit(limit)
    )
    orders = session.exec(order_query).all()

    count_stmt = select(func.count()).select_from(Order).where(Order.user_id == user_id)
    total = int(session.exec(count_stmt).one())

    collection = OrderCollection(
        items=[OrderRead.model_validate(order) for order in orders],
        count=total,
        links=PaginationLinks(self=str(request.url), next=None, prev=None),
    )

    next_offset = offset + limit
    prev_offset = max(offset - limit, 0)
    links_header = [f"<{str(request.url)}>; rel=\"self\""]

    if next_offset < total:
        next_url = str(request.url.include_query_params(offset=next_offset, limit=limit))
        collection.links.next = next_url
        links_header.append(f"<{next_url}>; rel=\"next\"")
    if offset > 0:
        prev_url = str(request.url.include_query_params(offset=prev_offset, limit=limit))
        collection.links.prev = prev_url
        links_header.append(f"<{prev_url}>; rel=\"prev\"")

    etag = _compute_etag(collection)
    headers = {
        "ETag": etag,
        "Cache-Control": "no-cache",
        "X-Total-Count": str(total),
        "Link": ", ".join(links_header),
    }
    return _json_response(collection, headers=headers)