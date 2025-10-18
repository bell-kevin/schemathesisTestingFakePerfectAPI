"""Order API endpoints."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func
from sqlmodel import Session, select

from ..db import get_session
from ..models import AuditLog, Item, Order, OrderStatus, User
from ..schemas import OrderCollection, OrderCreate, OrderRead, OrderUpdate, PaginationLinks, ProblemDetail
from ..security import Principal, require_order_write_principal

router = APIRouter(prefix="/orders", tags=["Orders"])

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

INVENTORY = {
    "LPT-1000": ("Analytical Engine Manual", Decimal("125.50")),
    "COB-1959": ("COBOL Specification", Decimal("89.90")),
    "ALG-0001": ("Algorithm Notes", Decimal("21.00")),
}


def _compute_etag(payload: object) -> str:
    encoded = json.dumps(jsonable_encoder(payload, by_alias=True), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f'W/"{hashlib.sha256(encoded).hexdigest()}"'


def _json_response(payload: object, *, status_code: int = 200, headers: Optional[dict[str, str]] = None) -> Response:
    return Response(
        status_code=status_code,
        content=json.dumps(jsonable_encoder(payload), ensure_ascii=False, separators=(",", ":")),
        media_type="application/json; charset=utf-8",
        headers=headers,
    )


@router.get(
    "",
    response_model=OrderCollection,
    summary="List orders",
    operation_id="listOrders",
    responses={
        200: {
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
                "X-Total-Count": {"schema": {"type": "integer"}},
                "Link": {"schema": {"type": "string"}},
            }
        }
    },
)
async def list_orders(
    request: Request,
    session: Session = Depends(get_session),
    status_filter: Optional[OrderStatus] = Query(default=None, alias="status"),
    from_date: Optional[datetime] = Query(default=None, alias="from"),
    to_date: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Response:
    filters = []
    if status_filter:
        filters.append(Order.status == status_filter)
    if from_date:
        if from_date.tzinfo is None:
            from_date = from_date.replace(tzinfo=timezone.utc)
        filters.append(Order.placed_at >= from_date)
    if to_date:
        if to_date.tzinfo is None:
            to_date = to_date.replace(tzinfo=timezone.utc)
        filters.append(Order.placed_at <= to_date)

    statement = select(Order)
    if filters:
        statement = statement.where(and_(*filters))
    statement = statement.order_by(Order.placed_at.desc(), Order.id).offset(offset).limit(limit)
    orders = session.exec(statement).all()

    count_stmt = select(func.count()).select_from(Order)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
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


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create order",
    operation_id="createOrder",
    responses={
        201: {
            "headers": {
                "Location": {"schema": {"type": "string", "format": "uri"}},
                "ETag": {"schema": {"type": "string"}},
            }
        },
        400: {
            "description": "Invalid order payload.",
            "content": PROBLEM_CONTENT,
        },
        404: {
            "description": "User not found.",
            "content": PROBLEM_CONTENT,
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def create_order(
    request: Request,
    order_in: OrderCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_order_write_principal()),
) -> Response:
    user = session.get(User, order_in.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    counts = Counter(order_in.item_skus)
    items = []
    total = Decimal("0.00")
    for sku, quantity in counts.items():
        inventory = INVENTORY.get(sku)
        if not inventory:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown SKU: {sku}")
        name, unit_price = inventory
        total += unit_price * quantity
        items.append((sku, name, quantity, unit_price))

    total = total.quantize(Decimal("0.01"))
    if total != order_in.total:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Total does not match item prices")

    now = datetime.now(timezone.utc)
    order = Order(
        id=uuid4(),
        user_id=order_in.user_id,
        status=order_in.status,
        total=total,
        placed_at=now,
        updated_at=now,
    )
    session.add(order)
    session.flush()

    for sku, name, quantity, unit_price in items:
        item = Item(order_id=order.id, sku=sku, name=name, quantity=quantity, unit_price=unit_price)
        session.add(item)

    audit = AuditLog(
        user_id=order.user_id,
        order_id=order.id,
        action="order.created",
        summary=f"Order created with {sum(counts.values())} items",
        performed_at=now,
    )
    session.add(audit)
    session.commit()
    session.refresh(order)

    body = OrderRead.model_validate(order)
    etag = _compute_etag(body)
    headers = {
        "Location": str(request.url_for("getOrder", order_id=order.id)),
        "ETag": etag,
        "Cache-Control": "no-cache",
    }
    return _json_response(body, status_code=status.HTTP_201_CREATED, headers=headers)


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Retrieve order",
    operation_id="getOrder",
    responses={
        200: {
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}
        },
        404: {
            "description": "Order not found.",
            "content": PROBLEM_CONTENT,
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def get_order(order_id: UUID, session: Session = Depends(get_session)) -> Response:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    body = OrderRead.model_validate(order)
    etag = _compute_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(body, headers=headers)


@router.put(
    "/{order_id}",
    response_model=OrderRead,
    summary="Replace order",
    operation_id="replaceOrder",
    responses={
        200: {
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}
        },
        404: {
            "description": "Order not found.",
            "content": PROBLEM_CONTENT,
        },
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
async def replace_order(
    order_id: UUID,
    order_in: OrderUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_order_write_principal()),
) -> Response:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order_in.status is not None:
        order.status = order_in.status
    if order_in.total is not None:
        order.total = order_in.total.quantize(Decimal("0.01"))
    order.updated_at = datetime.now(timezone.utc)

    session.add(order)
    session.commit()
    session.refresh(order)

    body = OrderRead.model_validate(order)
    etag = _compute_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(body, headers=headers)


@router.patch(
    "/{order_id}",
    response_model=OrderRead,
    summary="Update order",
    operation_id="updateOrder",
    responses={
        200: {
            "headers": {"ETag": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}
        },
        404: {
            "description": "Order not found.",
            "content": {"application/problem+json": {"schema": ProblemDetail.model_json_schema()}},
        },
    },
)
async def update_order(
    order_id: UUID,
    order_in: OrderUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_order_write_principal()),
) -> Response:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order_in.status is not None:
        order.status = order_in.status
    if order_in.total is not None:
        order.total = order_in.total.quantize(Decimal("0.01"))
    order.updated_at = datetime.now(timezone.utc)

    session.add(order)
    session.commit()
    session.refresh(order)

    body = OrderRead.model_validate(order)
    etag = _compute_etag(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    return _json_response(body, headers=headers)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete order",
    operation_id="deleteOrder",
    responses={
        204: {"description": "Order deleted."},
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: {
            "description": "Order not found.",
            "content": PROBLEM_CONTENT,
        },
    },
)
async def delete_order(
    order_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_order_write_principal()),
) -> Response:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    session.delete(order)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
