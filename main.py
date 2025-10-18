"""Self-contained FastAPI application for Schemathesis-friendly complex API."""
from __future__ import annotations

import html
import hashlib
import itertools
from enum import Enum
import json
import threading
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from http import HTTPStatus
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    UUID4,
    ValidationError,
    condecimal,
    conint,
    constr,
    model_validator,
)

from starlette.routing import Match


class Settings(BaseModel):
    """Application settings."""

    auth_token: str = "demo-token"
    model_config = ConfigDict(frozen=True)


_settings_instance = Settings()


def get_settings() -> Settings:
    """Provide application settings."""

    return _settings_instance


app = FastAPI(
    title="Fake Perfect API",
    version="1.0.0",
    description="A comprehensive FastAPI application built for Schemathesis demonstrations.",
    contact={
        "name": "API Support",
        "url": "https://example.com/support",
        "email": "support@example.com",
    },
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    default_response_class=JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

MAX_BODY_SIZE = 64 * 1024


class Link(BaseModel):
    """HAL-style link representation."""

    href: HttpUrl


class PaginationLinks(BaseModel):
    """Pagination link container."""

    self: HttpUrl
    next: Optional[HttpUrl] = None
    prev: Optional[HttpUrl] = None


class ProfileModel(BaseModel):
    """User profile details."""

    bio: Optional[constr(max_length=280)] = Field(
        default=None, description="Short biography", examples=["Backend engineer and API enthusiast."]
    )
    website: Optional[HttpUrl] = Field(
        default=None, description="Personal website URL", examples=["https://example.dev"]
    )
    interests: Optional[List[constr(strip_whitespace=True, min_length=1, max_length=60)]] = Field(
        default=None,
        description="Areas of interest",
        max_items=10,
        examples=[["fastapi", "testing"]],
    )

    @model_validator(mode="after")
    def ensure_unique_interests(self) -> "ProfileModel":
        interests = self.interests or []
        if len(interests) != len(set(map(str.lower, interests))):
            raise ValueError("Interests must be unique (case-insensitive).")
        return self


class UserRole(str, Enum):
    admin = "admin"
    member = "member"
    viewer = "viewer"


class UserBase(BaseModel):
    """Common user fields."""

    email: EmailStr = Field(examples=["sam@example.com"])
    name: constr(min_length=1, max_length=80) = Field(examples=["Sam Taylor"])
    role: UserRole = Field(examples=[UserRole.member])
    profile: Optional[ProfileModel] = Field(default=None, description="Optional profile information")


class UserCreate(UserBase):
    """Payload for creating a user."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "email": "jane.doe@example.com",
            "name": "Jane Doe",
            "role": "admin",
            "profile": {
                "bio": "Product leader and open-source contributor.",
                "website": "https://janedoe.dev",
                "interests": ["architecture", "apis"],
            },
        }
    })


class UserUpdate(BaseModel):
    """Partial update payload for a user."""

    email: Optional[EmailStr] = None
    name: Optional[constr(min_length=1, max_length=80)] = None
    role: Optional[UserRole] = None
    profile: Optional[ProfileModel] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "Janet Doe",
            "profile": {"bio": "Refined bio", "interests": ["testing", "documentation"]},
        }
    })


class UserOut(UserBase):
    """User response payload."""

    id: UUID4
    created_at: datetime

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": str(uuid4()),
            "email": "jane.doe@example.com",
            "name": "Jane Doe",
            "role": "admin",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "profile": {
                "bio": "Product leader and open-source contributor.",
                "website": "https://janedoe.dev",
                "interests": ["architecture", "apis"],
            },
        }
    })


class UserListResponse(BaseModel):
    """Paginated response for users."""

    items: List[UserOut]
    page: int
    page_size: int
    total: int
    _links: PaginationLinks

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [UserOut.model_config["json_schema_extra"]["example"]],
            "page": 1,
            "page_size": 25,
            "total": 1,
            "_links": {
                "self": "https://api.example.com/users?page=1&page_size=25",
                "next": None,
                "prev": None,
            },
        }
    })


class Dimensions(BaseModel):
    """Product dimensions."""

    w: float = Field(gt=0, description="Width in centimeters")
    h: float = Field(gt=0, description="Height in centimeters")
    d: float = Field(gt=0, description="Depth in centimeters")


Sku = constr(pattern=r"^SKU-[A-Z0-9]{6}$")


class ProductCategory(str, Enum):
    book = "book"
    device = "device"
    clothing = "clothing"


class ProductBase(BaseModel):
    """Common product fields."""

    sku: Sku = Field(examples=["SKU-ABC123"])
    name: constr(min_length=1, max_length=120) = Field(examples=["Wireless Keyboard"])
    price: condecimal(ge=0, max_digits=12, decimal_places=2) = Field(examples=["99.99"])
    category: ProductCategory = Field(examples=[ProductCategory.device])
    tags: List[constr(min_length=1, max_length=30)] = Field(
        default_factory=list,
        description="Product tags",
        max_items=15,
        examples=[["wireless", "peripheral"]],
    )
    dimensions: Optional[Dimensions] = Field(default=None)

    @model_validator(mode="after")
    def ensure_unique_tags(self) -> "ProductBase":
        tags = self.tags or []
        if len(tags) != len(set(map(str.lower, tags))):
            raise ValueError("Tags must be unique (case-insensitive).")
        return self


class ProductCreate(ProductBase):
    """Payload for creating products."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "sku": "SKU-DEV456",
            "name": "Developer Hoodie",
            "price": "59.50",
            "category": "clothing",
            "tags": ["comfortable", "unisex"],
            "dimensions": {"w": 55.0, "h": 70.0, "d": 2.0},
        }
    })


class ProductUpdate(ProductBase):
    """Payload for updating products via PUT."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "sku": "SKU-DEV456",
            "name": "Developer Hoodie (2024)",
            "price": "64.00",
            "category": "clothing",
            "tags": ["comfortable", "unisex", "2024"],
            "dimensions": {"w": 55.0, "h": 70.0, "d": 2.0},
        }
    })


class ProductOut(ProductBase):
    """Product response."""

    id: conint(strict=True, gt=0) = Field(examples=[1])

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 1,
            "sku": "SKU-DEV456",
            "name": "Developer Hoodie",
            "price": "59.50",
            "category": "clothing",
            "tags": ["comfortable", "unisex"],
            "dimensions": {"w": 55.0, "h": 70.0, "d": 2.0},
        }
    })


class ProductListResponse(BaseModel):
    """Paginated product list."""

    items: List[ProductOut]
    page: int
    page_size: int
    total: int
    _links: PaginationLinks

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [ProductOut.model_config["json_schema_extra"]["example"]],
            "page": 1,
            "page_size": 25,
            "total": 1,
            "_links": {
                "self": "https://api.example.com/products?page=1&page_size=25",
                "next": None,
                "prev": None,
            },
        }
    })


class OrderStatus(str, Enum):
    new = "new"
    paid = "paid"
    shipped = "shipped"
    cancelled = "cancelled"


class PaymentMethod(str, Enum):
    card = "card"
    paypal = "paypal"


class OrderItemPayload(BaseModel):
    """Order line item."""

    product_id: conint(strict=True, gt=0)
    qty: conint(strict=True, ge=1, le=100)

    model_config = ConfigDict(json_schema_extra={"example": {"product_id": 1, "qty": 2}})


class OrderCreate(BaseModel):
    """Order creation payload."""

    user_id: UUID4
    items: List[OrderItemPayload] = Field(min_length=1, max_items=50)
    payment_method: PaymentMethod
    notes: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user_id": str(uuid4()),
            "items": [{"product_id": 1, "qty": 2}],
            "payment_method": PaymentMethod.card.value,
            "notes": "Please deliver during business hours.",
        }
    })

    @model_validator(mode="after")
    def ensure_unique_products(self) -> "OrderCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate products are not allowed in a single order.")
        return self


class OrderItemOut(OrderItemPayload):
    """Order item response."""

    line_total: condecimal(ge=0, max_digits=12, decimal_places=2)

    model_config = ConfigDict(json_schema_extra={
        "example": {"product_id": 1, "qty": 2, "line_total": "119.00"}
    })


class OrderLinks(BaseModel):
    """HAL links for orders."""

    self: Link
    user: Link
    items: List[Link]


class OrderOut(BaseModel):
    """Order response payload."""

    id: UUID4
    user_id: UUID4
    status: OrderStatus
    created_at: datetime
    payment_method: PaymentMethod
    notes: Optional[str] = None
    total: condecimal(ge=0, max_digits=12, decimal_places=2)
    items: List[OrderItemOut]
    _links: OrderLinks

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "status": OrderStatus.new.value,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "payment_method": PaymentMethod.card.value,
            "notes": "Please deliver during business hours.",
            "total": "199.98",
            "items": [{"product_id": 1, "qty": 2, "line_total": "199.98"}],
            "_links": {
                "self": {"href": "https://api.example.com/orders/123"},
                "user": {"href": "https://api.example.com/users/456"},
                "items": [
                    {"href": "https://api.example.com/products/1"},
                    {"href": "https://api.example.com/products/2"},
                ],
            },
        }
    })


class OrderListResponse(BaseModel):
    """Paginated order list."""

    items: List[OrderOut]
    page: int
    page_size: int
    total: int
    _links: PaginationLinks

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "items": [OrderOut.model_config["json_schema_extra"]["example"]],
            "page": 1,
            "page_size": 25,
            "total": 1,
            "_links": {
                "self": "https://api.example.com/orders?page=1&page_size=25",
                "next": None,
                "prev": None,
            },
        }
    })


class OrderStatusUpdate(BaseModel):
    """Payload for updating order status."""

    status: OrderStatus

    model_config = ConfigDict(json_schema_extra={
        "example": {"status": "paid"}
    })


class EchoRequest(BaseModel):
    """Echo body."""

    message: constr(min_length=1, max_length=200)
    repeat: conint(ge=1, le=10)
    uppercase: bool

    model_config = ConfigDict(json_schema_extra={
        "example": {"message": "hello", "repeat": 2, "uppercase": True}
    })


class EchoResponse(BaseModel):
    """Echo response."""

    echoed: str
    original_message_length: int

    model_config = ConfigDict(json_schema_extra={
        "example": {"echoed": "HELLO HELLO", "original_message_length": 5}
    })


class StatusResponse(BaseModel):
    """Health status payload."""

    status: constr(pattern="^ok$") = Field(examples=["ok"])
    uptime_seconds: conint(ge=0) = Field(examples=[42])

    model_config = ConfigDict(json_schema_extra={
        "example": {"status": "ok", "uptime_seconds": 42}
    })


users_store: Dict[UUID, Dict[str, Any]] = {}
products_store: Dict[int, Dict[str, Any]] = {}
orders_store: Dict[UUID, Dict[str, Any]] = {}

users_lock = threading.Lock()
products_lock = threading.Lock()
orders_lock = threading.Lock()

product_id_sequence = itertools.count(start=1)


def quantize_price(value: Decimal) -> Decimal:
    """Ensure all decimal values use two decimal places."""

    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_etag(data: Any) -> str:
    """Generate a deterministic ETag for the supplied payload."""

    serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    return f'W/"{digest}"'


def build_rate_limit_headers(remaining: int = 999) -> Dict[str, str]:
    """Provide stub rate-limit headers."""

    return {
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Remaining": str(max(0, remaining)),
    }


def create_json_response(data: Any, status_code: int = 200, headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    """Create a JSON response with consistent headers."""

    merged_headers = {
        "Content-Type": "application/json; charset=utf-8",
        **build_rate_limit_headers(),
    }
    if headers:
        merged_headers.update(headers)
    return JSONResponse(content=data, status_code=status_code, headers=merged_headers)


def problem_response(
    request: Request,
    status_code: int,
    detail: str,
    title: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """Produce an RFC7807-style problem response."""

    try:
        default_title = HTTPStatus(status_code).phrase
    except ValueError:
        default_title = "Error"
    payload = {
        "type": "about:blank",
        "title": title or default_title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    return create_json_response(payload, status_code=status_code, headers=headers)


@app.middleware("http")
async def enforce_body_size(request: Request, call_next):
    """Reject large bodies and ensure consistent content type."""

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return problem_response(request, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Request body too large.")
        except ValueError as exc:
            return problem_response(request, status.HTTP_400_BAD_REQUEST, "Invalid Content-Length header.")

    if request.method in {"POST", "PUT", "PATCH"} and content_length is None:
        body = await request.body()
        if len(body) > MAX_BODY_SIZE:
            return problem_response(request, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Request body too large.")
        request._body = body

    response = await call_next(request)
    if response.headers.get("Content-Type") == "application/json":
        response.headers["Content-Type"] = "application/json; charset=utf-8"
    if "X-RateLimit-Limit" not in response.headers:
        response.headers.update(build_rate_limit_headers())
    return response


auth_scheme = HTTPBearer(auto_error=False)


def require_bearer_token(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)
) -> None:
    """Ensure write operations carry the correct bearer token."""

    settings = get_settings()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.credentials != settings.auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors as structured problem responses."""

    detail_messages = [
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()
    ]
    detail = "; ".join(detail_messages)
    return problem_response(request, status.HTTP_422_UNPROCESSABLE_ENTITY, detail or "Validation error.")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap HTTP exceptions in problem JSON while preserving headers."""

    headers = dict(exc.headers or {})
    if exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED and "Allow" not in headers:
        allowed_methods = set()
        for route in app.routes:
            if isinstance(route, APIRoute):
                match, _ = route.matches(request.scope)
                if match in {Match.FULL, Match.PARTIAL}:
                    allowed_methods.update(route.methods or [])
        if allowed_methods:
            headers["Allow"] = ", ".join(sorted(allowed_methods))
    try:
        title = HTTPStatus(exc.status_code).phrase
    except ValueError:
        title = "Error"
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    return problem_response(request, exc.status_code, detail, title=title, headers=headers)


@app.exception_handler(ValidationError)
async def pydantic_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle internal validation issues consistently."""

    detail_messages = [
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()
    ]
    return problem_response(request, status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(detail_messages))


@app.on_event("startup")
async def startup_event() -> None:
    """Seed the in-memory datastore and start the uptime timer."""

    app.state.start_time = time.time()
    if not users_store:
        seed_users()
    if not products_store:
        seed_products()
    if not orders_store:
        seed_orders()


def seed_users() -> None:
    """Populate default users."""

    now = datetime.utcnow()
    initial_users = [
        {
            "id": uuid4(),
            "email": "admin@example.com",
            "name": "Admin User",
            "role": "admin",
            "created_at": now,
            "profile": {
                "bio": "Administrator of the system.",
                "website": "https://admin.example.com",
                "interests": ["security", "compliance"],
            },
        },
        {
            "id": uuid4(),
            "email": "member@example.com",
            "name": "Member User",
            "role": "member",
            "created_at": now,
            "profile": {
                "bio": "Standard member.",
                "interests": ["apis", "testing"],
            },
        },
    ]
    with users_lock:
        for user in initial_users:
            users_store[user["id"]] = user


def seed_products() -> None:
    """Populate default products."""

    initial_products = [
        {
            "id": next(product_id_sequence),
            "sku": "SKU-BOOK01",
            "name": "API Design Book",
            "price": Decimal("39.90"),
            "category": "book",
            "tags": ["architecture", "best-practices"],
            "dimensions": {"w": 15.0, "h": 23.0, "d": 2.5},
        },
        {
            "id": next(product_id_sequence),
            "sku": "SKU-DEV999",
            "name": "Mechanical Keyboard",
            "price": Decimal("129.99"),
            "category": "device",
            "tags": ["mechanical", "keyboard"],
            "dimensions": {"w": 45.0, "h": 4.0, "d": 15.0},
        },
    ]
    with products_lock:
        for product in initial_products:
            products_store[product["id"]] = product


def seed_orders() -> None:
    """Populate default orders referencing seeded users and products."""

    if not users_store or not products_store:
        return
    order_id = uuid4()
    user_id = next(iter(users_store.keys()))
    first_product_id = next(iter(products_store.keys()))
    order = {
        "id": order_id,
        "user_id": user_id,
        "status": OrderStatus.new.value,
        "created_at": datetime.utcnow(),
        "payment_method": PaymentMethod.card.value,
        "notes": "Initial seeded order.",
        "items": [
            {"product_id": first_product_id, "qty": 1},
        ],
    }
    with orders_lock:
        orders_store[order_id] = order


def ensure_email_unique(email: str, user_id: Optional[UUID] = None) -> None:
    """Validate email uniqueness."""

    with users_lock:
        for existing_id, user in users_store.items():
            if user["email"].lower() == email.lower() and existing_id != user_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use.")


def ensure_sku_unique(sku: str, product_id: Optional[int] = None) -> None:
    """Validate SKU uniqueness."""

    with products_lock:
        for existing_id, product in products_store.items():
            if product["sku"].upper() == sku.upper() and existing_id != product_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already in use.")


def ensure_user_exists(user_id: UUID) -> Dict[str, Any]:
    """Fetch user or raise 404."""

    with users_lock:
        user = users_store.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def ensure_product_exists(product_id: int) -> Dict[str, Any]:
    """Fetch product or raise 404."""

    with products_lock:
        product = products_store.get(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


def ensure_order_exists(order_id: UUID) -> Dict[str, Any]:
    """Fetch order or raise 404."""

    with orders_lock:
        order = orders_store.get(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


def make_pagination_links(request: Request, page: int, page_size: int, total: int) -> PaginationLinks:
    """Build pagination links for responses."""

    query_params = dict(request.query_params)
    query_params.update({"page": page, "page_size": page_size})
    self_link = str(request.url.include_query_params(**query_params))

    next_link = None
    if page * page_size < total:
        query_params["page"] = page + 1
        next_link = str(request.url.include_query_params(**query_params))

    prev_link = None
    if page > 1:
        query_params["page"] = page - 1
        prev_link = str(request.url.include_query_params(**query_params))

    return PaginationLinks(self=self_link, next=next_link, prev=prev_link)


def order_to_response(order: Dict[str, Any], request: Request) -> OrderOut:
    """Transform internal order representation into response model."""

    user = ensure_user_exists(order["user_id"])
    items_out: List[OrderItemOut] = []
    item_links: List[Link] = []
    total = Decimal("0.00")

    for item in order["items"]:
        product = ensure_product_exists(item["product_id"])
        price = quantize_price(product["price"])
        line_total = quantize_price(price * item["qty"])
        total += line_total
        items_out.append(
            OrderItemOut(product_id=product["id"], qty=item["qty"], line_total=line_total)
        )
        item_links.append(Link(href=str(request.url_for("get_product", product_id=product["id"]))))

    total = quantize_price(total)
    links = OrderLinks(
        self=Link(href=str(request.url_for("get_order", order_id=order["id"]))),
        user=Link(href=str(request.url_for("get_user", user_id=user["id"]))),
        items=item_links,
    )
    return OrderOut(
        id=order["id"],
        user_id=order["user_id"],
        status=order["status"],
        created_at=order["created_at"],
        payment_method=order["payment_method"],
        notes=order.get("notes"),
        total=total,
        items=items_out,
        _links=links,
    )


@app.get("/users", response_model=UserListResponse, operation_id="listUsers")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    sort: str = Query(
        "created_at",
        pattern="^-?created_at$|^email$",
        description="Sort key",
    ),
) -> JSONResponse:
    """List users with pagination and sorting."""

    with users_lock:
        users = list(users_store.values())

    reverse = False
    key = sort
    if sort.startswith("-"):
        reverse = True
        key = sort[1:]

    users.sort(key=lambda u: u[key], reverse=reverse)

    total = len(users)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = users[start:end]

    items = [UserOut(**user) for user in paginated]
    links = make_pagination_links(request, page, page_size, total)
    payload = UserListResponse(items=items, page=page, page_size=page_size, total=total, _links=links)
    return create_json_response(payload.model_dump())


@app.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_bearer_token)],
    operation_id="createUser",
)
async def create_user(request: Request, user: UserCreate = Body(...)) -> JSONResponse:
    """Create a new user ensuring unique email addresses."""

    ensure_email_unique(user.email)
    new_user = {
        "id": uuid4(),
        "email": user.email,
        "name": user.name,
        "role": user.role.value if isinstance(user.role, UserRole) else user.role,
        "created_at": datetime.utcnow(),
        "profile": user.profile.model_dump() if user.profile else None,
    }
    with users_lock:
        users_store[new_user["id"]] = new_user
    response_model = UserOut(**new_user)
    headers = {
        "Location": str(request.url_for("get_user", user_id=new_user["id"])),
        **build_rate_limit_headers(remaining=998),
    }
    return create_json_response(response_model.model_dump(), status_code=status.HTTP_201_CREATED, headers=headers)


@app.get("/users/{user_id}", response_model=UserOut, operation_id="getUser")
async def get_user(request: Request, user_id: UUID4 = Path(...)) -> Response:
    """Fetch a single user, honoring conditional requests via ETags."""

    user = ensure_user_exists(UUID(str(user_id)))
    response_model = UserOut(**user)
    payload = response_model.model_dump()
    etag = generate_etag(payload)
    if request.headers.get("if-none-match") == etag:
        response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        response.headers["ETag"] = etag
        response.headers.update(build_rate_limit_headers())
        return response
    headers = {"ETag": etag}
    return create_json_response(payload, headers=headers)


@app.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_bearer_token)],
    operation_id="updateUser",
)
async def update_user(
    user_id: UUID4,
    request: Request,
    payload: UserUpdate = Body(...),
) -> JSONResponse:
    """Update mutable fields of a user."""

    stored = ensure_user_exists(UUID(str(user_id)))
    update_data = payload.model_dump(exclude_unset=True)
    if "email" in update_data:
        ensure_email_unique(update_data["email"], stored["id"])
    if "profile" in update_data:
        profile_value = update_data["profile"]
        update_data["profile"] = profile_value.model_dump() if profile_value else None
    if "role" in update_data:
        role_value = update_data["role"]
        update_data["role"] = role_value.value if isinstance(role_value, UserRole) else role_value
    stored.update(update_data)
    with users_lock:
        users_store[stored["id"]] = stored
    return create_json_response(UserOut(**stored).model_dump())


@app.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer_token)],
    operation_id="deleteUser",
)
async def delete_user(user_id: UUID4) -> Response:
    """Delete a user."""

    uuid = UUID(str(user_id))
    ensure_user_exists(uuid)
    with users_lock:
        users_store.pop(uuid, None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers.update(build_rate_limit_headers())
    return response


@app.get("/products", response_model=ProductListResponse, operation_id="listProducts")
async def list_products(
    request: Request,
    category: Optional[ProductCategory] = Query(
        default=None,
        description="Filter by category",
    ),
    q: Optional[str] = Query(default=None, min_length=1, description="Substring search over product name"),
    min_price: Optional[condecimal(ge=0, max_digits=12, decimal_places=2)] = Query(default=None),
    max_price: Optional[condecimal(ge=0, max_digits=12, decimal_places=2)] = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> JSONResponse:
    """List products with rich filtering semantics."""

    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_price must be <= max_price.")

    with products_lock:
        products = list(products_store.values())

    if category:
        category_value = category.value if isinstance(category, ProductCategory) else category
        products = [p for p in products if p["category"] == category_value]
    if q:
        products = [p for p in products if q.lower() in p["name"].lower()]
    if min_price is not None:
        products = [p for p in products if p["price"] >= Decimal(min_price)]
    if max_price is not None:
        products = [p for p in products if p["price"] <= Decimal(max_price)]

    products.sort(key=lambda p: p["id"])

    total = len(products)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = products[start:end]

    items = [ProductOut(**{**product, "price": quantize_price(product["price"])}) for product in paginated]
    links = make_pagination_links(request, page, page_size, total)
    payload = ProductListResponse(items=items, page=page, page_size=page_size, total=total, _links=links)
    return create_json_response(payload.model_dump())


@app.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_bearer_token)],
    operation_id="createProduct",
)
async def create_product(request: Request, product: ProductCreate = Body(...)) -> JSONResponse:
    """Create a product while enforcing SKU uniqueness."""

    ensure_sku_unique(product.sku)
    with products_lock:
        product_id = next(product_id_sequence)
        new_product = {
            "id": product_id,
            "sku": product.sku,
            "name": product.name,
            "price": Decimal(product.price),
            "category": product.category.value if isinstance(product.category, ProductCategory) else product.category,
            "tags": product.tags,
            "dimensions": product.dimensions.model_dump() if product.dimensions else None,
        }
        products_store[product_id] = new_product
    response_model = ProductOut(**{**new_product, "price": quantize_price(new_product["price"])})
    headers = {
        "Location": str(request.url_for("get_product", product_id=product_id)),
        **build_rate_limit_headers(remaining=998),
    }
    return create_json_response(response_model.model_dump(), status_code=status.HTTP_201_CREATED, headers=headers)


@app.get("/products/{product_id}", response_model=ProductOut, operation_id="getProduct")
async def get_product(request: Request, product_id: int = Path(..., gt=0)) -> Response:
    """Retrieve a product by ID with ETag support."""

    product = ensure_product_exists(product_id)
    response_model = ProductOut(**{**product, "price": quantize_price(product["price"])})
    payload = response_model.model_dump()
    etag = generate_etag(payload)
    if request.headers.get("if-none-match") == etag:
        response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        response.headers["ETag"] = etag
        response.headers.update(build_rate_limit_headers())
        return response
    headers = {"ETag": etag}
    return create_json_response(payload, headers=headers)


@app.put(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_bearer_token)],
    operation_id="replaceProduct",
)
async def replace_product(
    product_id: int = Path(..., gt=0),
    product: ProductUpdate = Body(...),
) -> JSONResponse:
    """Replace a product entry entirely."""

    ensure_product_exists(product_id)
    ensure_sku_unique(product.sku, product_id)
    updated = {
        "id": product_id,
        "sku": product.sku,
        "name": product.name,
        "price": Decimal(product.price),
        "category": product.category.value if isinstance(product.category, ProductCategory) else product.category,
        "tags": product.tags,
        "dimensions": product.dimensions.model_dump() if product.dimensions else None,
    }
    with products_lock:
        products_store[product_id] = updated
    response_model = ProductOut(**{**updated, "price": quantize_price(updated["price"])})
    return create_json_response(response_model.model_dump())


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer_token)],
    operation_id="deleteProduct",
)
async def delete_product(product_id: int = Path(..., gt=0)) -> Response:
    """Delete a product."""

    ensure_product_exists(product_id)
    with products_lock:
        products_store.pop(product_id, None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers.update(build_rate_limit_headers())
    return response


@app.get("/orders", response_model=OrderListResponse, operation_id="listOrders")
async def list_orders(
    request: Request,
    user_id: Optional[UUID4] = Query(default=None),
    since: Optional[datetime] = Query(default=None, description="Filter orders created after the provided timestamp"),
    status_filter: Optional[OrderStatus] = Query(
        default=None,
        alias="status",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> JSONResponse:
    """List orders with optional filters."""

    with orders_lock:
        orders = list(orders_store.values())

    if user_id is not None:
        orders = [o for o in orders if str(o["user_id"]) == str(user_id)]
    if since is not None:
        orders = [o for o in orders if o["created_at"] >= since]
    if status_filter is not None:
        status_value = status_filter.value if isinstance(status_filter, OrderStatus) else status_filter
        orders = [o for o in orders if o["status"] == status_value]

    orders.sort(key=lambda o: o["created_at"], reverse=True)

    total = len(orders)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = orders[start:end]

    items = [order_to_response(order, request) for order in paginated]
    links = make_pagination_links(request, page, page_size, total)
    payload = OrderListResponse(items=items, page=page, page_size=page_size, total=total, _links=links)
    return create_json_response(payload.model_dump())


@app.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_bearer_token)],
    operation_id="createOrder",
)
async def create_order(request: Request, order: OrderCreate = Body(...)) -> JSONResponse:
    """Create a new order with computed totals."""

    ensure_user_exists(UUID(str(order.user_id)))
    normalized_items = []
    for item in order.items:
        product = ensure_product_exists(item.product_id)
        normalized_items.append({"product_id": product["id"], "qty": item.qty})

    new_order = {
        "id": uuid4(),
        "user_id": UUID(str(order.user_id)),
        "status": OrderStatus.new.value,
        "created_at": datetime.utcnow(),
        "payment_method": order.payment_method.value if isinstance(order.payment_method, PaymentMethod) else order.payment_method,
        "notes": order.notes,
        "items": normalized_items,
    }
    with orders_lock:
        orders_store[new_order["id"]] = new_order
    response_model = order_to_response(new_order, request)
    headers = {
        "Location": str(request.url_for("get_order", order_id=new_order["id"])),
        **build_rate_limit_headers(remaining=998),
    }
    return create_json_response(response_model.model_dump(), status_code=status.HTTP_201_CREATED, headers=headers)


@app.get("/orders/{order_id}", response_model=OrderOut, operation_id="getOrder")
async def get_order(request: Request, order_id: UUID4 = Path(...)) -> Response:
    """Retrieve an order by ID with ETag support."""

    order = ensure_order_exists(UUID(str(order_id)))
    response_model = order_to_response(order, request)
    payload = response_model.model_dump()
    etag = generate_etag(payload)
    if request.headers.get("if-none-match") == etag:
        response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        response.headers["ETag"] = etag
        response.headers.update(build_rate_limit_headers())
        return response
    headers = {"ETag": etag}
    return create_json_response(payload, headers=headers)


@app.patch(
    "/orders/{order_id}",
    response_model=OrderOut,
    dependencies=[Depends(require_bearer_token)],
    operation_id="updateOrder",
)
async def update_order(
    order_id: UUID4,
    request: Request,
    status_payload: OrderStatusUpdate = Body(...),
) -> JSONResponse:
    """Update order status."""

    status_enum = status_payload.status
    order = ensure_order_exists(UUID(str(order_id)))
    order["status"] = status_enum.value
    with orders_lock:
        orders_store[order["id"]] = order
    return create_json_response(order_to_response(order, request).model_dump())


@app.delete(
    "/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer_token)],
    operation_id="deleteOrder",
)
async def delete_order(order_id: UUID4) -> Response:
    """Cancel (delete) an order."""

    uuid = UUID(str(order_id))
    ensure_order_exists(uuid)
    with orders_lock:
        orders_store.pop(uuid, None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers.update(build_rate_limit_headers())
    return response


@app.get("/status", response_model=StatusResponse, operation_id="getStatus")
async def get_status() -> JSONResponse:
    """Report service status and uptime."""

    uptime = int(time.time() - getattr(app.state, "start_time", time.time()))
    payload = StatusResponse(status="ok", uptime_seconds=uptime)
    return create_json_response(payload.model_dump())


@app.post("/echo", response_model=EchoResponse, dependencies=[Depends(require_bearer_token)], operation_id="postEcho")
async def echo(payload: EchoRequest = Body(...)) -> JSONResponse:
    """Echo validated content with optional transformation."""

    sanitized = html.escape(payload.message)
    message = (sanitized + " ") * payload.repeat
    message = message.strip()
    if payload.uppercase:
        message = message.upper()
    response_model = EchoResponse(echoed=message, original_message_length=len(payload.message))
    return create_json_response(response_model.model_dump())


@app.options("/users", operation_id="optionsUsers")
async def options_users() -> Response:
    """Explicit OPTIONS handler for /users."""

    headers = {"Allow": "GET, HEAD, POST, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/users/{user_id}", operation_id="optionsUser")
async def options_user() -> Response:
    """Explicit OPTIONS handler for user detail."""

    headers = {"Allow": "GET, HEAD, PATCH, DELETE, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/products", operation_id="optionsProducts")
async def options_products() -> Response:
    """Explicit OPTIONS handler for /products."""

    headers = {"Allow": "GET, HEAD, POST, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/products/{product_id}", operation_id="optionsProduct")
async def options_product() -> Response:
    """Explicit OPTIONS handler for product detail."""

    headers = {"Allow": "GET, HEAD, PUT, DELETE, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/orders", operation_id="optionsOrders")
async def options_orders() -> Response:
    """Explicit OPTIONS handler for /orders."""

    headers = {"Allow": "GET, HEAD, POST, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/orders/{order_id}", operation_id="optionsOrder")
async def options_order() -> Response:
    """Explicit OPTIONS handler for order detail."""

    headers = {"Allow": "GET, HEAD, PATCH, DELETE, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/status", operation_id="optionsStatus")
async def options_status() -> Response:
    """Explicit OPTIONS handler for /status."""

    headers = {"Allow": "GET, HEAD, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@app.options("/echo", operation_id="optionsEcho")
async def options_echo() -> Response:
    """Explicit OPTIONS handler for /echo."""

    headers = {"Allow": "POST, OPTIONS"}
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)


"""Run instructions:
1. Install dependencies: `pip install fastapi uvicorn`.
2. Start the server: `uvicorn main:app`.
"""
