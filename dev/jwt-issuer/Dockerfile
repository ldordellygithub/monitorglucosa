# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 AS uv

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN addgroup --system --gid 10001 issuer \
    && adduser --system --uid 10001 --ingroup issuer --no-create-home issuer
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
USER issuer
EXPOSE 9000
CMD ["/app/.venv/bin/uvicorn", "src.jwt_issuer.main:create_issuer_app", "--factory", "--host", "0.0.0.0", "--port", "9000", "--no-access-log"]
