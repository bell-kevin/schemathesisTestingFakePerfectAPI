FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md schemathesis.toml /app/
COPY app /app/app
COPY tests /app/tests
COPY openapi-static /app/openapi-static
COPY uvicorn_app.sh /app/uvicorn_app.sh

RUN pip install --upgrade pip \
    && pip install . \
    && chmod +x /app/uvicorn_app.sh

EXPOSE 8000

CMD ["/app/uvicorn_app.sh"]
