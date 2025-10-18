# Perfect Schema API

This repository contains a production-grade FastAPI application that exposes a rich,
contract-driven API surface. It is intentionally designed to exercise Schemathesis and
other contract-testing tools with realistic patterns including authentication, pagination,
filtering, nested resources, and strict error handling.

## Features

- **FastAPI + SQLModel + SQLite** persistence layer with deterministic seed data
- **OAuth2 password flow** and **API key** authentication with JWT-backed tokens
- Comprehensive resource coverage for users and orders including filtering, sorting,
and conditional requests (ETag / `If-None-Match`)
- Strict RFC 7807 problem details for all error responses
- CORS-enabled, proper 405 handling with `Allow` header, full OPTIONS support
- Static OpenAPI 3.1 export kept in sync with the live schema

## Getting Started

### Requirements

- Python 3.11+
- Poetry/pip (any PEP 517 installer)

Install dependencies in editable mode:

```bash
python -m pip install --upgrade pip
pip install -e .
```

### Running the API

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Seed data is created automatically at startup with deterministic UUIDs and timestamps.
Use the `/status` endpoint to verify uptime and deployment metadata.

### Authentication Reference

| Flow          | Details                                                     |
| ------------- | ----------------------------------------------------------- |
| OAuth2 token  | `POST /token` with `username=admin`, `password=adminpass`   |
| Reader token  | `POST /token` with `username=reader`, `password=readerpass` |
| API key       | Add header `X-API-Key: service-key-1`                       |

Write operations (`POST`/`PUT`/`PATCH`/`DELETE`) require either a bearer token with the
appropriate scope (`users:write` or `orders:write`) or the API key.

### Schemathesis

Full contract test invocation used locally and in CI:

```bash
schemathesis run http://127.0.0.1:8000/openapi.json \
  --workers 32 \
  --checks all \
  --exclude-checks response_headers_conformance
```

For a faster fuzzing-only pass:

```bash
schemathesis run http://127.0.0.1:8000/openapi.json \
  --phases=fuzzing \
  --workers 32 \
  --checks all \
  --exclude-checks response_headers_conformance
```

Configuration is stored in [`schemathesis.toml`](schemathesis.toml), which disables
unexpected HTTP method exploration and null-byte payloads.

### Testing

```bash
pytest
```

The smoke suite verifies OpenAPI availability and ensures the committed static schema
matches the live application.

### Static OpenAPI Document

`openapi-static/openapi.json` is a checked-in snapshot of the generated schema. After
making API changes, re-export it with:

```bash
python - <<'PY'
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

schema = TestClient(app).get('/openapi.json').json()
Path('openapi-static/openapi.json').write_text(__import__('json').dumps(schema, indent=2))
PY
```

### Docker

Build and run the production image:

```bash
docker build -t perfect-schema-api .
docker run -p 8000:8000 perfect-schema-api
```

The container entrypoint launches Uvicorn with 2 workers, proxy header support, and
`--forwarded-allow-ips='*'` to operate correctly behind reverse proxies.

## Continuous Integration

GitHub Actions workflow [`contract.yml`](.github/workflows/contract.yml) installs the
package, boots the application, and executes Schemathesis with the full `--checks all`
configuration to guarantee contract conformance on every commit.
