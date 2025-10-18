"""Echo endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import EchoRequest, EchoResponse

router = APIRouter(prefix="", tags=["Utility"])


@router.post(
    "/echo",
    response_model=EchoResponse,
    summary="Echo a message",
    description="Return the provided message after applying requested transformations.",
    operation_id="echoMessage",
    responses={
        200: {
            "description": "Echoed payload.",
            "content": {
                "application/json; charset=utf-8": {
                    "example": {"message": "HELLO HELLO", "characters": 11}
                }
            },
        },
    },
)
async def echo(payload: EchoRequest) -> EchoResponse:
    """Echo the provided message."""

    message = payload.message.upper() if payload.uppercase else payload.message
    repeated = " ".join([message] * payload.repeat)
    return EchoResponse(message=repeated, characters=len(repeated))
