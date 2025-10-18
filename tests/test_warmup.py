"""Tests for the warm-up helpers used when exercising the remote service."""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import httpx
import pytest

from perfectapi.warmup import (
    ServiceUnavailableError,
    _build_schemathesis_command,
    run_remote_schemathesis,
    wait_for_service,
)


def test_wait_for_service_retries_until_success() -> None:
    """The helper should keep retrying until it receives a 200 response."""

    attempts = itertools.count()

    def handler(request: httpx.Request) -> httpx.Response:
        index = next(attempts)
        if index < 2:
            raise httpx.ConnectError("service asleep", request=request)
        return httpx.Response(200, request=request)

    transport = httpx.MockTransport(handler)
    wait_for_service("https://example.test", timeout=1.0, poll_interval=0.0, transport=transport)

    # Two failures plus a successful attempt.
    assert next(attempts) == 3


def test_wait_for_service_raises_when_timeout_expires() -> None:
    """A timeout should surface as a ServiceUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("still cold", request=request)

    transport = httpx.MockTransport(handler)
    with pytest.raises(ServiceUnavailableError):
        wait_for_service("https://example.test", timeout=0.1, poll_interval=0.0, transport=transport)


def test_build_schemathesis_command_includes_custom_arguments(tmp_path: Path) -> None:
    """The command builder should forward additional Schemathesis arguments."""

    spec_path = tmp_path / "schema.yaml"
    spec_path.write_text("openapi: 3.1.0\n")

    command = _build_schemathesis_command(
        base_url="https://service.test",
        spec_path=spec_path,
        request_timeout=42.0,
        extra_args=["--hypothesis-deadline", "250"],
    )

    assert command == [
        "uvx",
        "schemathesis",
        "run",
        str(spec_path),
        "--base-url",
        "https://service.test",
        "--request-timeout",
        "42.0",
        "--exclude-checks",
        "unsupported_method",
        "--hypothesis-deadline",
        "250",
    ]


def test_build_schemathesis_command_skips_default_exclusion_when_overridden(tmp_path: Path) -> None:
    """Supplying explicit check flags should prevent default exclusions."""

    spec_path = tmp_path / "schema.yaml"
    spec_path.write_text("openapi: 3.1.0\n")

    command = _build_schemathesis_command(
        base_url="https://service.test",
        spec_path=spec_path,
        request_timeout=42.0,
        extra_args=["--checks", "all"],
    )

    assert command == [
        "uvx",
        "schemathesis",
        "run",
        str(spec_path),
        "--base-url",
        "https://service.test",
        "--request-timeout",
        "42.0",
        "--checks",
        "all",
    ]


def test_build_schemathesis_command_handles_short_checks_flag(tmp_path: Path) -> None:
    """The short ``-c`` form should also disable default exclusions."""

    spec_path = tmp_path / "schema.yaml"
    spec_path.write_text("openapi: 3.1.0\n")

    command = _build_schemathesis_command(
        base_url="https://service.test",
        spec_path=spec_path,
        request_timeout=42.0,
        extra_args=["-c", "all"],
    )

    assert command == [
        "uvx",
        "schemathesis",
        "run",
        str(spec_path),
        "--base-url",
        "https://service.test",
        "--request-timeout",
        "42.0",
        "-c",
        "all",
    ]


def test_build_schemathesis_command_respects_custom_exclusions(tmp_path: Path) -> None:
    """Explicit ``--exclude-checks`` arguments should be preserved as-is."""

    spec_path = tmp_path / "schema.yaml"
    spec_path.write_text("openapi: 3.1.0\n")

    command = _build_schemathesis_command(
        base_url="https://service.test",
        spec_path=spec_path,
        request_timeout=42.0,
        extra_args=["--exclude-checks", "status_code_conformance"],
    )

    assert command == [
        "uvx",
        "schemathesis",
        "run",
        str(spec_path),
        "--base-url",
        "https://service.test",
        "--request-timeout",
        "42.0",
        "--exclude-checks",
        "status_code_conformance",
    ]


def test_run_remote_schemathesis_propagates_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """The orchestrator should return the exit code from Schemathesis."""

    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[int]:
        calls.append(command)
        completed = subprocess.CompletedProcess(command, returncode=7)
        return completed

    def fake_wait_for_service(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr("perfectapi.warmup.wait_for_service", fake_wait_for_service)
    monkeypatch.setattr("perfectapi.warmup.subprocess.run", fake_run)

    exit_code = run_remote_schemathesis(
        base_url="https://service.test",
        spec_path=Path("schema.yaml"),
        request_timeout=10.0,
        warmup_timeout=1.0,
        poll_interval=0.1,
        extra_args=["--checks", "all"],
    )

    assert exit_code == 7
    assert calls == [
        [
            "uvx",
            "schemathesis",
            "run",
            "schema.yaml",
            "--base-url",
            "https://service.test",
            "--request-timeout",
            "10.0",
            "--checks",
            "all",
        ]
    ]

