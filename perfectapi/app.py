"""Application definition for the fake perfect API.

This module exposes both the ASGI application instance and a factory function
for creating new instances.  The API is intentionally small and deterministic
so that Schemathesis can exercise all defined behaviours without encountering
unexpected server-side errors.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI
from pydantic import BaseModel, Field, StrictBool, constr, conint


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

    message: constr(min_length=1, max_length=1000)  # type: ignore[var-annotated]
    repeat: conint(ge=1, le=5) = 1  # type: ignore[var-annotated]
    uppercase: StrictBool = False


class EchoResponse(BaseModel):
    """Successful response payload for the echo endpoint."""

    result: str = Field(..., description="The transformed message.")
    length: conint(ge=0)  # type: ignore[var-annotated]
    repeat: conint(ge=1, le=5)  # type: ignore[var-annotated]
    uppercase: StrictBool


_METADATA: Final = ServiceMetadata()


def create_app() -> FastAPI:
    """Create a configured :class:`FastAPI` application."""

    application = FastAPI(title=_METADATA.title, version=_METADATA.version, description=_METADATA.description)

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

    return application


app = create_app()
