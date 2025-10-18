"""Application definition for the fake perfect API.

This module exposes both the ASGI application instance and a factory function
for creating new instances.  The API is intentionally small and deterministic
so that Schemathesis can exercise all defined behaviours without encountering
unexpected server-side errors.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, constr, conint
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_405_METHOD_NOT_ALLOWED


@dataclass(frozen=True)
class ServiceMetadata:
    """Metadata displayed in the generated OpenAPI document."""

    title: str = "Fake Perfect API"
    version: str = "1.0.0"
    description: str = (
        "A tiny API intentionally designed to have predictable behaviour. "
        "It exists so that Schemathesis-based tests can focus on the API "
        "contract rather than application logic."
    )


class StatusResponse(BaseModel):
    """Response schema for the status endpoint."""

    status: str = Field("ok", description="Health indicator for the service.")


class EchoRequest(BaseModel):
    """Input payload for the echo endpoint."""

    model_config = ConfigDict(extra="forbid")

    message: constr(min_length=1, max_length=1000)  # type: ignore[var-annotated]
    repeat: conint(ge=1, le=5) = 1  # type: ignore[var-annotated]
    uppercase: StrictBool = False


class EchoResponse(BaseModel):
    """Successful response payload for the echo endpoint."""

    result: str = Field(..., description="The transformed message.")
    length: conint(ge=0)  # type: ignore[var-annotated]
    repeat: conint(ge=1, le=5)  # type: ignore[var-annotated]
    uppercase: StrictBool


def _parse_query_boolean(value: bool | str) -> bool:
    """Parse boolean-like query parameters without accepting loose coercions."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "false"}:
            return normalized == "true"

    raise ValueError("Invalid boolean string")


StrictQueryBool = Annotated[bool, BeforeValidator(_parse_query_boolean)]


class InspectResponse(BaseModel):
    """Response payload for the message inspection endpoint."""

    message: constr(min_length=1, max_length=1000)  # type: ignore[var-annotated]
    mirrored: constr(min_length=1, max_length=1000)  # type: ignore[var-annotated]
    length: conint(ge=1, le=1000)  # type: ignore[var-annotated]
    is_palindrome: StrictBool
    case_sensitive: StrictBool


_METADATA: Final = ServiceMetadata()


def _allowed_methods(application: FastAPI, path: str) -> list[str]:
    """Return the HTTP methods supported by the application for the given path."""

    allowed: set[str] = set()

    for route in application.router.routes:
        path_regex = getattr(route, "path_regex", None)
        if path_regex is None or path_regex.match(path) is None:
            continue

        methods = getattr(route, "methods", None)
        if methods:
            allowed.update(methods)

    if "GET" in allowed:
        allowed.add("HEAD")

    if allowed:
        allowed.add("OPTIONS")

    return sorted(allowed)


class EnsureAllowHeaderMiddleware(BaseHTTPMiddleware):
    """Guarantee that 405 responses include an Allow header."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)

        if response.status_code == HTTP_405_METHOD_NOT_ALLOWED:
            allowed_methods = _allowed_methods(request.app, request.scope["path"])
            if allowed_methods:
                allow_header = ", ".join(allowed_methods)
                if response.headers.get("allow") != allow_header:
                    response.headers["Allow"] = allow_header

        return response


def create_app() -> FastAPI:
    """Create a configured :class:`FastAPI` application."""

    application = FastAPI(title=_METADATA.title, version=_METADATA.version, description=_METADATA.description)
    application.add_middleware(EnsureAllowHeaderMiddleware)

    @application.get("/status", response_model=StatusResponse, tags=["health"])
    async def read_status() -> StatusResponse:
        """Return the current status of the service."""

        return StatusResponse()

    @application.post("/echo", response_model=EchoResponse, tags=["utilities"])
    async def echo(payload: EchoRequest) -> EchoResponse:
        """Return the provided message after applying deterministic transformations."""

        message = payload.message.upper() if payload.uppercase else payload.message
        result = message * payload.repeat
        return EchoResponse(result=result, length=len(result), repeat=payload.repeat, uppercase=payload.uppercase)

    @application.get("/inspect", response_model=InspectResponse, tags=["utilities"])
    async def inspect(
        message: Annotated[
            str,
            Query(
                min_length=1,
                max_length=1000,
                description="Message to analyse for palindromic properties.",
            ),
        ],
        case_sensitive: Annotated[
            StrictQueryBool,
            Query(
                description="If false, the palindrome check ignores character casing.",
            ),
        ] = True,
    ) -> InspectResponse:
        """Analyse a message and report simple textual characteristics."""

        normalized = message if case_sensitive else message.casefold()
        mirrored = message[::-1]
        is_palindrome = normalized == normalized[::-1]
        return InspectResponse(
            message=message,
            mirrored=mirrored,
            length=len(message),
            is_palindrome=is_palindrome,
            case_sensitive=case_sensitive,
        )

    return application


app = create_app()
