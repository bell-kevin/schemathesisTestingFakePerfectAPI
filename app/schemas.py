"""Pydantic schemas shared by the API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, StrictInt, StrictStr

from .models import OrderStatus


class ProblemDetail(BaseModel):
    """RFC 7807 compatible problem details."""

    type: StrictStr = Field(default="about:blank", examples=["https://example.com/problems/not-found"])
    title: StrictStr = Field(examples=["Resource not found"])
    status: StrictInt = Field(ge=100, le=599, examples=[404])
    detail: StrictStr = Field(examples=["User with id ... was not found"])
    instance: StrictStr = Field(examples=["/users/123"])


class StatusResponse(BaseModel):
    """Application status payload."""

    model_config = ConfigDict(title="StatusResponse")

    status: Literal["ok"] = Field(examples=["ok"])
    version: StrictStr = Field(examples=["1.0.0"])
    uptime_seconds: float = Field(ge=0, examples=[1234.56])
    monotonic_timestamp: float = Field(ge=0, examples=[98765.432])


class EchoRequest(BaseModel):
    """Input for the echo endpoint."""

    message: StrictStr = Field(min_length=1, max_length=500, examples=["Hello"])
    repeat: StrictInt = Field(default=1, ge=1, le=10, examples=[2])
    uppercase: StrictBool = Field(default=False, examples=[True])


class EchoResponse(BaseModel):
    """Echoed message response."""

    message: StrictStr = Field(examples=["HELLO HELLO"])
    characters: StrictInt = Field(ge=0, examples=[10])


class PaginationLinks(BaseModel):
    """Link relations for paginated endpoints."""

    model_config = ConfigDict(extra="forbid")

    self: StrictStr = Field(examples=["/users?offset=0&limit=20"])
    next: Optional[StrictStr] = Field(default=None, examples=["/users?offset=10&limit=5"])
    prev: Optional[StrictStr] = Field(default=None, examples=["/users?offset=0&limit=5"])


class AuditLogEntry(BaseModel):
    """Audit log entry returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: StrictStr
    summary: StrictStr
    performed_at: datetime


class UserBase(BaseModel):
    """Common fields for user schemas."""

    email: EmailStr = Field(examples=["user@example.com"])
    full_name: StrictStr = Field(min_length=1, max_length=200, examples=["Ada Lovelace"])
    is_active: bool = Field(default=True, examples=[True])


class UserCreate(UserBase):
    """Schema for creating users."""

    pass


class UserUpdate(BaseModel):
    """Partial update schema for users."""

    email: Optional[EmailStr] = None
    full_name: Optional[StrictStr] = Field(default=None, min_length=1, max_length=200)
    is_active: Optional[bool] = None


class UserPatch(UserUpdate):
    """Alias for PATCH operations."""

    pass


class UserRead(UserBase):
    """User representation in responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    joined_at: datetime
    updated_at: datetime


class UserDetail(UserRead):
    """Detailed user representation including related resources."""

    audit_logs: List[AuditLogEntry] = Field(default_factory=list)


class UserCollection(BaseModel):
    """Response for user list endpoints."""

    items: List[UserRead] = Field(default_factory=list)
    count: StrictInt = Field(ge=0, examples=[3])
    links: PaginationLinks


class OrderBase(BaseModel):
    """Common fields for orders."""

    status: OrderStatus = Field(default=OrderStatus.PENDING)
    total: Decimal = Field(gt=Decimal("0"), examples=[Decimal("125.50")])


class OrderCreate(OrderBase):
    """Schema for creating orders."""

    user_id: UUID = Field(examples=["00000000-0000-0000-0000-000000000001"])
    item_skus: List[StrictStr] = Field(min_length=1, max_length=10, examples=[["SKU-1"]])


class OrderUpdate(BaseModel):
    """Schema for updating orders."""

    status: Optional[OrderStatus] = None
    total: Optional[Decimal] = Field(default=None, gt=Decimal("0"))


class OrderRead(OrderBase):
    """Order representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    placed_at: datetime
    updated_at: datetime


class OrderCollection(BaseModel):
    """Response for order list."""

    items: List[OrderRead] = Field(default_factory=list)
    count: StrictInt = Field(ge=0)
    links: PaginationLinks


class TokenRequest(BaseModel):
    """OAuth2 password grant request payload."""

    username: StrictStr = Field(examples=["admin"])
    password: StrictStr = Field(examples=["secret"])
    scope: StrictStr = Field(default="", examples=["users:write orders:write"])


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: StrictStr
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: StrictInt = Field(ge=0, examples=[3600])
    scope: StrictStr = Field(default="")


class APIKeyInfo(BaseModel):
    """Metadata about provided API keys."""

    key: StrictStr
    name: StrictStr


class OrderFilterParams(BaseModel):
    """Filter parameters for order listing."""

    status: Optional[OrderStatus] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

