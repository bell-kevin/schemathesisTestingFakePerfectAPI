"""Test suite for the Fake Perfect API application."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from perfectapi.app import EchoResponse, ServiceMetadata, create_app


@pytest.fixture()
def client() -> TestClient:
    """Provide a TestClient bound to a fresh application instance."""

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_application_metadata() -> None:
    """The application should expose the expected metadata."""

    app = create_app()
    metadata = ServiceMetadata()

    assert app.title == metadata.title
    assert app.version == metadata.version
    assert app.description == metadata.description


def test_status_endpoint_returns_ok(client: TestClient) -> None:
    """The status endpoint should respond with an OK payload."""

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_echo_endpoint_repeats_message(client: TestClient) -> None:
    """Echo endpoint should repeat the message without transformation by default."""

    response = client.post("/echo", json={"message": "abc"})

    assert response.status_code == 200
    assert response.json() == {
        "result": "abc",
        "length": 3,
        "repeat": 1,
        "uppercase": False,
    }


def test_echo_endpoint_handles_uppercase_and_repeat(client: TestClient) -> None:
    """Echo endpoint should honour the uppercase flag and repeat count."""

    response = client.post(
        "/echo",
        json={"message": "Hi", "repeat": 3, "uppercase": True},
    )

    expected = EchoResponse(result="HIHIHI", length=6, repeat=3, uppercase=True)

    assert response.status_code == 200
    assert response.json() == expected.model_dump()


def test_echo_endpoint_rejects_invalid_repeat(client: TestClient) -> None:
    """The endpoint should reject repeat counts outside the allowed range."""

    response = client.post("/echo", json={"message": "abc", "repeat": 6})

    assert response.status_code == 422
    body = response.json()
    assert body["detail"][0]["loc"] == ["body", "repeat"]
    assert body["detail"][0]["type"] == "less_than_equal"


def test_inspect_endpoint_detects_palindromes(client: TestClient) -> None:
    """The inspect endpoint should report palindrome information."""

    response = client.get("/inspect", params={"message": "level"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "level",
        "mirrored": "level",
        "length": 5,
        "is_palindrome": True,
        "case_sensitive": True,
    }


def test_inspect_endpoint_supports_case_insensitive_checks(client: TestClient) -> None:
    """Case-insensitive palindrome detection should be available via a query flag."""

    response = client.get("/inspect", params={"message": "Level", "case_sensitive": False})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Level",
        "mirrored": "leveL",
        "length": 5,
        "is_palindrome": True,
        "case_sensitive": False,
    }


def test_status_unsupported_method_reports_allowed_methods(client: TestClient) -> None:
    """405 responses must advertise the methods supported for the resource."""

    response = client.request("TRACE", "/status")

    assert response.status_code == 405
    assert set(map(str.strip, response.headers["allow"].split(","))) == {"GET", "HEAD", "OPTIONS"}


def test_echo_unsupported_method_reports_allowed_methods(client: TestClient) -> None:
    """All endpoints should expose an Allow header on 405 responses."""

    response = client.request("TRACE", "/echo")

    assert response.status_code == 405
    assert set(map(str.strip, response.headers["allow"].split(","))) == {"OPTIONS", "POST"}
