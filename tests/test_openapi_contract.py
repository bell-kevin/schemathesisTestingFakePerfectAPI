"""Smoke tests for OpenAPI contract stability."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_openapi_schema_is_3_1() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["openapi"].startswith("3.1."), data["openapi"]
    assert "paths" in data


def test_status_endpoint_contract() -> None:
    response = client.get("/status")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    payload = response.json()
    assert payload["status"] == "ok"
    assert "uptime_seconds" in payload


def test_static_openapi_matches_runtime() -> None:
    static_path = Path("openapi-static/openapi.json")
    assert static_path.exists(), "Static OpenAPI export is missing"
    static_data = json.loads(static_path.read_text())
    live_data = client.get("/openapi.json").json()
    assert static_data == live_data
