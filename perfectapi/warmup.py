"""Utilities for interacting with the deployed Fake Perfect API service.

This module contains helpers that smooth over operational quirks of the
hosted instance on Render.  The free tier for that platform aggressively
hibernates idle services which means the first request after a period of
inactivity can take tens of seconds to complete.  Schemathesis applies a
10 second read timeout while downloading the remote OpenAPI document which
is frequently insufficient when the service is cold.  To make the
developer experience predictable we provide two facilities:

* :func:`wait_for_service` polls the deployed API until it becomes
  responsive or a deadline expires.
* :func:`run_remote_schemathesis` orchestrates the warm-up step followed by
  invoking Schemathesis with a local OpenAPI file so that schema loading is
  never subject to cold-start delays.

The module can be executed directly via ``python -m perfectapi.warmup``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

import httpx


DEFAULT_BASE_URL = "https://fake-perfect-api.onrender.com"
DEFAULT_SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi.yaml"
DEFAULT_STATUS_PATH = "/status"


class ServiceUnavailableError(RuntimeError):
    """Raised when the remote service never becomes ready within a deadline."""


def wait_for_service(
    base_url: str = DEFAULT_BASE_URL,
    *,
    status_path: str = DEFAULT_STATUS_PATH,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Block until the remote service responds with a healthy status.

    Parameters
    ----------
    base_url:
        The deployment base URL.  Any trailing slash is ignored to avoid
        generating URLs with ``//``.
    status_path:
        Relative path that returns a ``200`` response when the service is
        ready.  The default points at the lightweight ``/status`` endpoint.
    timeout:
        Maximum amount of seconds to wait for a healthy response.
    poll_interval:
        Amount of seconds to sleep between attempts.
    transport:
        Optional custom HTTP transport.  This is primarily intended for
        testing where an :class:`httpx.MockTransport` can be supplied.

    Raises
    ------
    ServiceUnavailableError
        If the deadline expires before a healthy response is observed.
    """

    normalized_base = base_url.rstrip("/")
    normalized_path = "/" + status_path.lstrip("/")
    target_url = f"{normalized_base}{normalized_path}"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    timeout_config = httpx.Timeout(timeout, read=timeout)
    with httpx.Client(timeout=timeout_config, transport=transport) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(target_url)
            except Exception as exc:  # pragma: no cover - httpx collapses exceptions.
                last_error = exc
            else:
                if response.status_code == 200:
                    return
                last_error = RuntimeError(
                    f"Received unexpected status {response.status_code} from {target_url}"
                )
            time.sleep(poll_interval)

    raise ServiceUnavailableError(
        f"Service at {target_url} did not become ready within {timeout} seconds"
    ) from last_error


def _build_schemathesis_command(
    *,
    base_url: str,
    spec_path: Path,
    request_timeout: float,
    extra_args: Iterable[str] = (),
) -> list[str]:
    """Compose the ``uvx schemathesis run`` command line."""

    command = [
        "uvx",
        "schemathesis",
        "run",
        str(spec_path),
        "--base-url",
        base_url,
        "--request-timeout",
        str(request_timeout),
    ]
    command.extend(extra_args)
    return command


def run_remote_schemathesis(
    *,
    base_url: str = DEFAULT_BASE_URL,
    spec_path: Path = DEFAULT_SPEC_PATH,
    request_timeout: float = 60.0,
    warmup_timeout: float = 120.0,
    poll_interval: float = 2.0,
    status_path: str = DEFAULT_STATUS_PATH,
    extra_args: Iterable[str] = (),
) -> int:
    """Warm the remote service and invoke Schemathesis.

    Returns the exit code of the Schemathesis process.
    """

    wait_for_service(
        base_url,
        status_path=status_path,
        timeout=warmup_timeout,
        poll_interval=poll_interval,
    )
    command = _build_schemathesis_command(
        base_url=base_url,
        spec_path=spec_path,
        request_timeout=request_timeout,
        extra_args=extra_args,
    )
    completed = subprocess.run(command, check=False)
    return completed.returncode


def parse_cli_arguments(arguments: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for the module CLI."""

    parser = argparse.ArgumentParser(
        description="Warm the Render deployment and execute Schemathesis against it.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL of the deployed API.",
    )
    parser.add_argument(
        "--spec-path",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help="Path to the OpenAPI schema file used for the run.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=60.0,
        help="Per-request timeout forwarded to Schemathesis.",
    )
    parser.add_argument(
        "--warmup-timeout",
        type=float,
        default=120.0,
        help="Maximum time to wait for the remote service to become ready.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Delay between readiness checks during warm-up.",
    )
    parser.add_argument(
        "--status-path",
        default=DEFAULT_STATUS_PATH,
        help="Endpoint used to probe service readiness.",
    )
    parser.add_argument(
        "schemathesis-args",
        nargs=argparse.REMAINDER,
        help=(
            "Additional options forwarded to Schemathesis. "
            "Prefix your arguments with '--' if the first option should be interpreted "
            "as a Schemathesis flag rather than a warm-up module flag."
        ),
    )

    namespace = parser.parse_args(arguments)

    extra_args = namespace.schemathesis_args or []
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]
    namespace.extra_args = extra_args
    return namespace


def main(arguments: list[str] | None = None) -> int:
    """Entry-point used when the module is executed as a script."""

    if arguments is None:
        arguments = sys.argv[1:]

    options = parse_cli_arguments(arguments)
    try:
        return run_remote_schemathesis(
            base_url=options.base_url,
            spec_path=options.spec_path,
            request_timeout=options.request_timeout,
            warmup_timeout=options.warmup_timeout,
            poll_interval=options.poll_interval,
            status_path=options.status_path,
            extra_args=options.extra_args,
        )
    except ServiceUnavailableError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised via manual invocation.
    raise SystemExit(main())
