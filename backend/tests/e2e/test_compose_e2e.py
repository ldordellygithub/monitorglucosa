"""Pruebas de punta a punta de la imagen Docker, .dockerignore y Docker Compose."""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
TEST_SUB_UUID = "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"


def _require_docker() -> str:
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        pytest.skip("Docker no está disponible en este entorno")
    probe = subprocess.run(
        [docker_bin, "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("El demonio de Docker no está accesible")
    return docker_bin


def _http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req_headers = dict(headers or {})
    if data is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, body
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        body = json.loads(raw) if raw else {}
        resp_headers = {k.lower(): v for k, v in err.headers.items()}
        return err.code, resp_headers, body


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.req("fase-1a:1.3")
def test_imagen_excluye_env_secretos_y_datos_y_usa_usuario_sin_privilegios(
    tmp_path: Path,
) -> None:
    """Un .env, *.pem y *.key en el contexto nunca entran en la imagen final."""
    docker_bin = _require_docker()
    context_dir = tmp_path / "backend_ctx"
    shutil.copytree(
        BACKEND_DIR,
        context_dir,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", ".mypy_cache"),
    )
    # Inyectar archivos sensibles y datos ficticios en raíz y dentro de src/ y src/api/
    for target_dir in (context_dir, context_dir / "src", context_dir / "src" / "api"):
        (target_dir / ".env").write_text("DATABASE_PASSWORD=secreto-ficticio\n")
        (target_dir / ".env.local").write_text("API_KEY=otro-secreto\n")
        (target_dir / "falso.pem").write_text("certificado-ficticio-para-prueba\n")
        (target_dir / "falso.key").write_text("clave-privada-ficticia\n")
        (target_dir / "registros.csv").write_text("fecha,valor\n2026-01-01,110\n")

    tag = f"monitorglucosa-api:e2e-ignore-{secrets.token_hex(4)}"
    try:
        build = subprocess.run(
            [
                docker_bin,
                "build",
                "--platform",
                "linux/amd64",
                "--provenance=false",
                "--sbom=false",
                "-t",
                tag,
                str(context_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert build.returncode == 0, build.stderr

        inspect_script = (
            "set -e; "
            "echo UID=$(id -u); "
            "find /app -path /app/.venv -prune -o "
            "\\( -name '.env*' -o -name '*.pem' -o -name '*.key' -o -name '*.csv' \\) "
            "-print"
        )
        run = subprocess.run(
            [
                docker_bin,
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                tag,
                "-c",
                inspect_script,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        output_lines = [
            line.strip() for line in run.stdout.splitlines() if line.strip()
        ]
        assert "UID=0" not in output_lines
        # Ningún archivo sensible o de datos debe aparecer en /app ni en /app/src/**
        assert not any("/app/" in line for line in output_lines), output_lines
    finally:
        subprocess.run([docker_bin, "rmi", "-f", tag], capture_output=True, check=False)


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.req("fase-1a:1.2")
def test_imagen_unica_arranca_con_cmd_de_lambda_y_responde_en_8080() -> None:
    """La imagen arranca con su CMD por defecto (uvicorn --no-access-log) en 8080."""
    docker_bin = _require_docker()
    tag = f"monitorglucosa-api:e2e-cmd-{secrets.token_hex(4)}"
    container_name = f"mg-e2e-cmd-{secrets.token_hex(4)}"
    host_port = 18080

    try:
        build = subprocess.run(
            [
                docker_bin,
                "build",
                "--platform",
                "linux/amd64",
                "--provenance=false",
                "--sbom=false",
                "-t",
                tag,
                str(BACKEND_DIR),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert build.returncode == 0, build.stderr

        # Verificar que el CMD de la imagen lleva --no-access-log y puerto 8080
        inspect_cmd = subprocess.run(
            [docker_bin, "inspect", "--format", "{{json .Config.Cmd}}", tag],
            capture_output=True,
            text=True,
            check=True,
        )
        cmd_list: list[str] = json.loads(inspect_cmd.stdout)
        assert "--no-access-log" in cmd_list
        assert "8080" in cmd_list
        assert "src.main:create_app" in cmd_list

        # Verificar LWA 1.1.0, PYTHONDONTWRITEBYTECODE=1 y bundle CA de RDS (1.2)
        lwa_check = subprocess.run(
            [
                docker_bin,
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                tag,
                "-c",
                (
                    "set -e; "
                    "test \"$PYTHONDONTWRITEBYTECODE\" = '1'; "
                    "test -x /opt/extensions/lambda-adapter; "
                    "grep -q 'BEGIN CERTIFICATE' "
                    "/etc/ssl/certs/rds-combined-ca-bundle.pem"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert lwa_check.returncode == 0, lwa_check.stderr

        # Arrancar SIN sobrescribir el CMD (exactamente como Lambda / Compose)
        start = subprocess.run(
            [
                docker_bin,
                "run",
                "-d",
                "--rm",
                "--name",
                container_name,
                "-p",
                f"127.0.0.1:{host_port}:8080",
                "-e",
                "ENVIRONMENT=local",
                "-e",
                "DATABASE_HOST=127.0.0.1",
                "-e",
                "DATABASE_PORT=5432",
                "-e",
                "DATABASE_NAME=monitorglucosa",
                "-e",
                "DATABASE_USER=mg_api",
                "-e",
                "DATABASE_PASSWORD=local-e2e-pass",
                "-e",
                "LOCAL_JWT_ISSUER=http://jwt-issuer:9000",
                "-e",
                "LOCAL_JWKS_URL=http://jwt-issuer:9000/.well-known/jwks.json",
                "-e",
                "LOCAL_JWT_CLIENT_IDS=web,collector",
                tag,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert start.returncode == 0, start.stderr

        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                status, headers, body = _http_request(
                    "GET", f"http://127.0.0.1:{host_port}/health"
                )
                assert status == 200
                assert body == {"status": "ok"}
                assert "x-request-id" in headers
                return
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)

        pytest.fail(f"La imagen no respondió en /health tras 20 s: {last_error}")
    finally:
        subprocess.run(
            [docker_bin, "stop", container_name], capture_output=True, check=False
        )
        subprocess.run([docker_bin, "rmi", "-f", tag], capture_output=True, check=False)


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.req("fase-1a:1.1", "fase-1a:3.3")
def test_compose_up_wait_levanta_stack_y_valida_jwt_del_emisor_local() -> None:
    """docker compose up --wait con .env.example levanta API, PG 16 y jwt-issuer."""
    docker_bin = _require_docker()
    project_name = f"mg-e2e-{secrets.token_hex(4)}"
    base_cmd = [
        docker_bin,
        "compose",
        "-p",
        project_name,
        "--env-file",
        str(ENV_EXAMPLE),
        "-f",
        str(REPO_ROOT / "compose.yaml"),
    ]

    try:
        up = subprocess.run(
            [*base_cmd, "up", "--build", "--wait"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert up.returncode == 0, f"STDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}"

        # 1. /health responde 200 (Requisito 1.1)
        status_h, headers_h, body_h = _http_request(
            "GET", "http://127.0.0.1:8000/health"
        )
        assert status_h == 200
        assert body_h == {"status": "ok"}
        assert "x-request-id" in headers_h

        # 2. /health/ready responde 200 (PostgreSQL 16 + bootstrap.sql + mg_api listos)
        status_r, _headers_r, body_r = _http_request(
            "GET", "http://127.0.0.1:8000/health/ready"
        )
        assert status_r == 200
        assert body_r == {"status": "ready"}

        # 3. Obtener un access token válido del emisor local (dev/jwt-issuer)
        status_tok, _h_tok, body_tok = _http_request(
            "POST",
            "http://127.0.0.1:9000/token",
            json_body={"sub": TEST_SUB_UUID, "client_id": "web"},
        )
        assert status_tok == 200
        access_token = body_tok["access_token"]

        # 4. GET /api/v1/me con token válido -> 200 {sub} (Requisitos 3.3, 3.5)
        status_me, _h_me, body_me = _http_request(
            "GET",
            "http://127.0.0.1:8000/api/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert status_me == 200
        assert body_me == {"sub": TEST_SUB_UUID}

        # 5. GET /api/v1/me con token alterado -> 401 UNAUTHENTICATED (Requisito 3.3)
        tampered = access_token[:-1] + ("A" if access_token[-1] != "A" else "B")
        status_bad, _h_bad, body_bad = _http_request(
            "GET",
            "http://127.0.0.1:8000/api/v1/me",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert status_bad == 401
        assert body_bad["code"] == "UNAUTHENTICATED"

        # 6. GET /api/v1/me sin token -> 401 UNAUTHENTICATED
        status_none, _h_none, body_none = _http_request(
            "GET", "http://127.0.0.1:8000/api/v1/me"
        )
        assert status_none == 401
        assert body_none["code"] == "UNAUTHENTICATED"
    finally:
        subprocess.run(
            [*base_cmd, "down", "-v", "--remove-orphans"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
