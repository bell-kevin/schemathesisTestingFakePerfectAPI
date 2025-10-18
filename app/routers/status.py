"""Status endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, status

from ..schemas import StatusResponse
from ..version import APP_VERSION

router = APIRouter(prefix="", tags=["Status"])

ALLOWED_METHODS = ("GET", "HEAD")


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Service status",
    description="Return service health, uptime, and monotonic timestamp information.",
    operation_id="getStatus",
    responses={
        200: {
            "description": "Status payload.",
            "content": {"application/json; charset=utf-8": {"example": {"status": "ok", "version": APP_VERSION, "uptime_seconds": 1.23, "monotonic_timestamp": 12345.6}}},
        }
    },
)
async def get_status(request: Request) -> StatusResponse:
    """Report API health information."""

    start_time: float = getattr(request.app.state, "start_time", time.monotonic())
    uptime = max(time.monotonic() - start_time, 0.0)
    return StatusResponse(
        status="ok",
        version=APP_VERSION,
        uptime_seconds=uptime,
        monotonic_timestamp=time.monotonic(),
    )


@router.api_route("/status", methods=["TRACE"], include_in_schema=False)
async def status_trace() -> None:
    """Return a 405 response with an Allow header for unsupported TRACE requests."""

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
        headers={"Allow": ", ".join(ALLOWED_METHODS)},
    )
