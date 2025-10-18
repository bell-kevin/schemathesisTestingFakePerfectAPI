#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 2 \
  --proxy-headers \
  --forwarded-allow-ips='*'
