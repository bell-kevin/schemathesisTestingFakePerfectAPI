"""Status endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from ..schemas import StatusResponse
from ..version import APP_VERSION

router = APIRouter(prefix="", tags=["Status"])


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
