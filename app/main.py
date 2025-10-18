"""Application entrypoint."""

from __future__ import annotations

import json
import time
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Match

from . import routers
from .db import init_db
from .schemas import ProblemDetail, TokenResponse
from .security import issue_token
from .version import APP_VERSION


class UTF8JSONResponse(JSONResponse):
    """JSON response that always declares UTF-8."""

    media_type = "application/json; charset=utf-8"


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_OPENAPI_PATH = BASE_DIR / "openapi-static" / "openapi.json"


app = FastAPI(
    title="Perfect Schema API",
    summary="A deliberately precise API for contract testing.",
    version=APP_VERSION,
    openapi_version="3.1.0",
    default_response_class=UTF8JSONResponse,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "API Support", "email": "support@example.com"},
    license_info={"name": "Apache-2.0"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    app.state.start_time = time.monotonic()
    init_db()


async def problem_response(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    type_: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        type=type_ or f"https://httpstatuses.com/{status_code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=status_code,
        content=json.loads(problem.model_dump_json()),
        media_type="application/problem+json",
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return await problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Validation error",
        detail or "Request validation failed",
        type_="https://example.com/problems/validation-error",
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    title = exc.detail if isinstance(exc.detail, str) and exc.detail else HTTPStatus(exc.status_code).phrase
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    return await problem_response(request, exc.status_code, title, detail, headers=exc.headers)


@app.middleware("http")
async def ensure_allow_header(request: Request, call_next):  # type: ignore[override]
    response = await call_next(request)
    if response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        allow = response.headers.get("Allow")
        if not allow:
            methods: set[str] = set()
            for route in request.app.routes:
                if isinstance(route, APIRoute):
                    match, _ = route.matches(request.scope)
                    if match is Match.FULL:
                        methods.update(route.methods or [])
            if methods:
                response.headers["Allow"] = ", ".join(sorted(methods))
    return response


@app.post(
    "/token",
    summary="OAuth2 token",
    operation_id="issueToken",
    tags=["Auth"],
    response_model=TokenResponse,
    responses={
        200: {
            "description": "OAuth2 access token.",
            "content": {
                "application/json; charset=utf-8": {
                    "example": {
                        "access_token": "token-value",
                        "token_type": "bearer",
                        "expires_in": 3600,
                        "scope": "users:write orders:write",
                    }
                }
            },
        }
    },
)
async def token_endpoint(token: TokenResponse = Depends(issue_token)) -> TokenResponse:
    return token


app.include_router(routers.status.router)
app.include_router(routers.echo.router)
app.include_router(routers.users.router)
app.include_router(routers.orders.router)


@lru_cache(maxsize=1)
def _load_static_openapi_schema() -> dict:
    """Load the static OpenAPI schema bundled with the project."""

    if not STATIC_OPENAPI_PATH.exists():
        msg = "Static OpenAPI export is missing; regenerate the bundled schema before deployment."
        raise RuntimeError(msg)
    return json.loads(STATIC_OPENAPI_PATH.read_text())


def custom_openapi() -> dict:
    """Serve the bundled OpenAPI document instead of regenerating it."""

    if app.openapi_schema:
        return app.openapi_schema

    schema = _load_static_openapi_schema()
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
