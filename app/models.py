"""Database models for the API."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Numeric
from sqlmodel import Field, Relationship, SQLModel


class OrderStatus(str, Enum):
    """Enumeration of the lifecycle states of an order."""

    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class User(SQLModel, table=True):
    """A person registered in the system."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str
    is_active: bool = Field(default=True, index=True)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    orders: List["Order"] = Relationship(back_populates="user")
    audit_logs: List["AuditLog"] = Relationship(back_populates="user")


class Order(SQLModel, table=True):
    """A purchase order placed by a user."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    status: OrderStatus = Field(default=OrderStatus.PENDING, index=True)
    total: Decimal = Field(
        sa_column=Column(Numeric(precision=12, scale=2)),
        default=Decimal("0.00"),
    )
    placed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional[User] = Relationship(back_populates="orders")
    items: List["Item"] = Relationship(back_populates="order")
    audit_logs: List["AuditLog"] = Relationship(back_populates="order")


class Item(SQLModel, table=True):
    """An individual item included in an order."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="order.id", index=True)
    sku: str = Field(index=True)
    name: str
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(
        sa_column=Column(Numeric(precision=12, scale=2)),
        default=Decimal("0.00"),
    )

    order: Optional[Order] = Relationship(back_populates="items")


class AuditLog(SQLModel, table=True):
    """Record of significant events for users and orders."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    order_id: Optional[UUID] = Field(default=None, foreign_key="order.id")
    action: str
    summary: str
    performed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    user: Optional[User] = Relationship(back_populates="audit_logs")
    order: Optional[Order] = Relationship(back_populates="audit_logs")
