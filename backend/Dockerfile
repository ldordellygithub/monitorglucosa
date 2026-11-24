# syntax=docker/dockerfile:1.7
# Imagen única de la API y del migrator: local (Compose), CI y AWS Lambda (ADR 0005, ADR 0006).
# Construir con: docker build --platform linux/amd64 --provenance=false --sbom=false backend

FROM ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 AS uv

FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 AS lwa

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev \
    && python -c "import pathlib, urllib.request; p = pathlib.Path('/tmp/rds-combined-ca-bundle.pem'); urllib.request.urlretrieve('https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem', p); assert 'BEGIN CERTIFICATE' in p.read_text(encoding='utf-8')"

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN addgroup --system --gid 10001 appuser \
    && adduser --system --uid 10001 --ingroup appuser --no-create-home appuser
COPY --from=lwa /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=builder /tmp/rds-combined-ca-bundle.pem /etc/ssl/certs/rds-combined-ca-bundle.pem
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./alembic.ini
COPY src ./src
RUN chmod 0444 /etc/ssl/certs/rds-combined-ca-bundle.pem \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "src.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
