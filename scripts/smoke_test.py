"""Prueba de humo post-despliegue contra HTTP API (Requisitos 7.5 y NFR-2, ADR 0009).

Comprueba dos invariantes sobre el despliegue recién promovido:
1. `GET /health/ready` firmado con SigV4 (`execute-api`) responde 200 con cuerpo
   `{"status": "ready"}`, reintentando 503/5xx o timeouts hasta 120 s respetando
   `Retry-After`, con timeout de 40 s por petición.
2. `GET /api/v1/me` sin token responde 401.

Solo imprime rutas, códigos de estado y tiempos (nunca cuerpos, cabeceras ni tokens).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials
from botocore.exceptions import BotoCoreError
from botocore.session import Session

DEFAULT_REGION = "us-east-1"
DEFAULT_MAX_WAIT_S = 120.0
DEFAULT_REQUEST_TIMEOUT_S = 40.0
DEFAULT_RETRY_DELAY_S = 5.0
MIN_RETRY_AFTER_S = 1.0
MAX_RETRY_AFTER_S = 30.0
NFR2_BUDGET_S = 60.0

REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-\d+$")


class SmokeTestError(RuntimeError):
    """Fallo en alguna verificación de la prueba de humo."""


@dataclass(frozen=True)
class SmokeTestConfig:
    """Parámetros validados para ejecutar la prueba de humo."""

    api_endpoint: str
    region: str = DEFAULT_REGION
    max_wait_s: float = DEFAULT_MAX_WAIT_S
    request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    default_retry_delay_s: float = DEFAULT_RETRY_DELAY_S


@dataclass(frozen=True)
class SmokeTestResult:
    """Resumen seguro (solo códigos de estado y tiempos) de la prueba de humo."""

    ready_status: int
    ready_attempts: int
    ready_elapsed_ms: int
    unauth_status: int
    unauth_elapsed_ms: int

    @property
    def within_nfr2_budget(self) -> bool:
        """Indica si `/health/ready` respondió 200 dentro del objetivo NFR-2 (≤ 60s)."""
        return self.ready_elapsed_ms <= int(NFR2_BUDGET_S * 1000)


class RequestSigner(Protocol):
    """Firma una petición GET y devuelve las cabeceras firmadas."""

    def sign_get(self, url: str) -> Mapping[str, str]:
        """Genera cabeceras de autenticación para `GET url`."""
        ...


class BotocoreSigV4Signer:
    """Firmador AWS SigV4 para API Gateway (`execute-api`) usando botocore."""

    def __init__(
        self,
        *,
        region: str,
        service: str = "execute-api",
        credentials: ReadOnlyCredentials | None = None,
    ) -> None:
        self._region = region
        self._service = service
        self._credentials = credentials

    def _resolve_credentials(self) -> ReadOnlyCredentials:
        if self._credentials is not None:
            return self._credentials
        try:
            session = Session()
            creds = session.get_credentials()
            if creds is None:
                raise SmokeTestError(
                    "No se encontraron credenciales de AWS para firmar "
                    "/health/ready con SigV4."
                )
            return creds.get_frozen_credentials()
        except BotoCoreError as exc:
            raise SmokeTestError(
                "Error al obtener credenciales de AWS para firmar SigV4."
            ) from exc

    def sign_get(self, url: str) -> Mapping[str, str]:
        """Firma una solicitud `GET` con SigV4 y devuelve cabeceras planas."""
        credentials = self._resolve_credentials()
        try:
            aws_request = AWSRequest(method="GET", url=url)
            SigV4Auth(credentials, self._service, self._region).add_auth(aws_request)
        except BotoCoreError as exc:
            raise SmokeTestError(
                "Error al firmar la petición /health/ready con AWS SigV4."
            ) from exc
        return dict(aws_request.headers.items())


def _validate_config(config: SmokeTestConfig) -> str:
    raw_endpoint = config.api_endpoint.strip()
    if any(ch.isspace() or ord(ch) < 32 for ch in raw_endpoint):
        raise SmokeTestError("api_endpoint no puede contener espacios ni control.")

    parsed = urlsplit(raw_endpoint)
    if parsed.scheme != "https":
        raise SmokeTestError("api_endpoint debe usar HTTPS.")
    if not parsed.hostname:
        raise SmokeTestError("api_endpoint debe incluir un nombre de host válido.")
    if parsed.username is not None or parsed.password is not None:
        raise SmokeTestError("api_endpoint no debe contener credenciales embebidas.")
    if parsed.query or parsed.fragment:
        raise SmokeTestError("api_endpoint no debe incluir query ni fragmento.")

    if not REGION_PATTERN.match(config.region.strip()):
        raise SmokeTestError("region no es una región de AWS válida.")
    if not math.isfinite(config.max_wait_s) or config.max_wait_s < 0:
        raise SmokeTestError("max_wait_s debe ser un número finito mayor o igual a 0.")
    if not math.isfinite(config.request_timeout_s) or config.request_timeout_s <= 0:
        raise SmokeTestError("request_timeout_s debe ser finito y positivo.")
    if (
        not math.isfinite(config.default_retry_delay_s)
        or config.default_retry_delay_s < 0
    ):
        raise SmokeTestError("default_retry_delay_s debe ser finito y no negativo.")

    return raw_endpoint.rstrip("/")


def _parse_retry_after(header_value: str | None, fallback_s: float) -> float:
    """Interpreta `Retry-After` numérico finito y lo acota a `[1.0, 30.0]` s."""
    if header_value is None:
        return fallback_s
    stripped = header_value.strip()
    if not stripped:
        return fallback_s
    try:
        parsed = float(stripped)
    except ValueError:
        return fallback_s
    if not math.isfinite(parsed) or parsed < 0:
        return fallback_s
    return min(max(parsed, MIN_RETRY_AFTER_S), MAX_RETRY_AFTER_S)


def _is_ready_body(response: httpx.Response) -> bool:
    """Confirma que un 200 de `/health/ready` entrega `{"status": "ready"}`."""
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("status") == "ready"


def _check_health_ready(
    *,
    client: httpx.Client,
    url: str,
    signer: RequestSigner,
    config: SmokeTestConfig,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    emit: Callable[[str], None],
) -> tuple[int, int, int]:
    """Comprueba `GET /health/ready` firmado con SigV4 respetando `Retry-After`."""
    started = clock()
    deadline = started + config.max_wait_s
    attempts = 0

    while True:
        attempts += 1
        attempt_started = clock()
        headers = dict(signer.sign_get(url))

        retry_after_s: float | None = None
        last_status: int | None = None

        try:
            response = client.get(
                url,
                headers=headers,
                timeout=config.request_timeout_s,
            )
            last_status = response.status_code
            attempt_ms = int((clock() - attempt_started) * 1000)
            emit(
                f"[smoke_test] GET /health/ready intento={attempts} "
                f"status={last_status} duracion_ms={attempt_ms}"
            )

            if last_status == 200:
                if not _is_ready_body(response):
                    raise SmokeTestError(
                        "GET /health/ready respondió 200 pero el cuerpo "
                        "no tiene status='ready'."
                    )
                total_ms = int((clock() - started) * 1000)
                return last_status, attempts, total_ms

            if 500 <= last_status < 600:
                retry_after_s = _parse_retry_after(
                    response.headers.get("Retry-After"),
                    config.default_retry_delay_s,
                )
            else:
                raise SmokeTestError(
                    "GET /health/ready respondió estado no reintentable: "
                    f"{last_status}."
                )
        except (httpx.TimeoutException, httpx.TransportError):
            attempt_ms = int((clock() - attempt_started) * 1000)
            emit(
                f"[smoke_test] GET /health/ready intento={attempts} "
                f"status=network_error duracion_ms={attempt_ms}"
            )
            retry_after_s = config.default_retry_delay_s
        except httpx.HTTPError as exc:
            attempt_ms = int((clock() - attempt_started) * 1000)
            emit(
                f"[smoke_test] GET /health/ready intento={attempts} "
                f"status=http_client_error duracion_ms={attempt_ms}"
            )
            raise SmokeTestError(
                "Error de cliente HTTP al verificar GET /health/ready."
            ) from exc

        remaining = deadline - clock()
        if remaining <= 0:
            total_ms = int((clock() - started) * 1000)
            status_label = (
                str(last_status) if last_status is not None else "network_error"
            )
            raise SmokeTestError(
                "GET /health/ready no respondió 200 dentro de "
                f"{config.max_wait_s:.0f} s (intentos={attempts}, "
                f"ultimo_estado={status_label}, duracion_ms={total_ms})."
            )

        delay = (
            retry_after_s if retry_after_s is not None else config.default_retry_delay_s
        )
        wait_s = min(delay, remaining)
        emit(f"[smoke_test] reintento /health/ready espera_s={wait_s:.1f}")
        sleep(wait_s)


def _check_unauthenticated_me(
    *,
    client: httpx.Client,
    url: str,
    timeout_s: float,
    clock: Callable[[], float],
    emit: Callable[[str], None],
) -> tuple[int, int]:
    """Comprueba que `GET /api/v1/me` sin token responde 401."""
    started = clock()
    try:
        response = client.get(url, timeout=timeout_s)
    except httpx.HTTPError as exc:
        elapsed_ms = int((clock() - started) * 1000)
        emit(
            f"[smoke_test] GET /api/v1/me status=network_error duracion_ms={elapsed_ms}"
        )
        raise SmokeTestError(
            "Error de red al verificar GET /api/v1/me sin token."
        ) from exc

    elapsed_ms = int((clock() - started) * 1000)
    status = response.status_code
    emit(
        f"[smoke_test] GET /api/v1/me (sin token) "
        f"status={status} duracion_ms={elapsed_ms}"
    )
    if status != 401:
        raise SmokeTestError(
            f"GET /api/v1/me sin token debía responder 401, pero respondió {status}."
        )
    return status, elapsed_ms


def run_smoke_test(
    config: SmokeTestConfig,
    *,
    signer: RequestSigner | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> SmokeTestResult:
    """Ejecuta la prueba de humo (`/health/ready` SigV4 + `/api/v1/me` sin token)."""
    endpoint = _validate_config(config)
    active_signer = signer or BotocoreSigV4Signer(region=config.region.strip())
    emit = log or (lambda msg: print(msg, flush=True))

    ready_url = f"{endpoint}/health/ready"
    me_url = f"{endpoint}/api/v1/me"

    with httpx.Client(transport=transport, follow_redirects=False) as client:
        ready_status, ready_attempts, ready_elapsed_ms = _check_health_ready(
            client=client,
            url=ready_url,
            signer=active_signer,
            config=config,
            clock=clock,
            sleep=sleep,
            emit=emit,
        )
        unauth_status, unauth_elapsed_ms = _check_unauthenticated_me(
            client=client,
            url=me_url,
            timeout_s=config.request_timeout_s,
            clock=clock,
            emit=emit,
        )

    result = SmokeTestResult(
        ready_status=ready_status,
        ready_attempts=ready_attempts,
        ready_elapsed_ms=ready_elapsed_ms,
        unauth_status=unauth_status,
        unauth_elapsed_ms=unauth_elapsed_ms,
    )
    emit(
        f"[smoke_test] ok ready_status={result.ready_status} "
        f"ready_intentos={result.ready_attempts} ready_ms={result.ready_elapsed_ms} "
        f"within_nfr2={result.within_nfr2_budget} "
        f"unauth_status={result.unauth_status} unauth_ms={result.unauth_elapsed_ms}"
    )
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prueba de humo post-despliegue: /health/ready (SigV4) y /api/v1/me (401)."
        )
    )
    parser.add_argument(
        "--api-endpoint",
        default=os.environ.get("API_ENDPOINT", ""),
        help="URL HTTPS base de API Gateway (o env API_ENDPOINT).",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"Región de AWS para SigV4 (por defecto: {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--max-wait-s",
        type=float,
        default=DEFAULT_MAX_WAIT_S,
        help=(
            "Presupuesto total de reintentos para /health/ready "
            f"(por defecto: {DEFAULT_MAX_WAIT_S} s)."
        ),
    )
    parser.add_argument(
        "--request-timeout-s",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_S,
        help=(
            "Timeout por petición individual "
            f"(por defecto: {DEFAULT_REQUEST_TIMEOUT_S} s; ≥ 40 s)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada CLI."""
    args = _parse_args(argv)
    config = SmokeTestConfig(
        api_endpoint=args.api_endpoint,
        region=args.region,
        max_wait_s=args.max_wait_s,
        request_timeout_s=args.request_timeout_s,
    )
    try:
        run_smoke_test(config)
    except SmokeTestError as exc:
        print(f"[smoke_test] ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
