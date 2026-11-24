"""Pruebas unitarias de `scripts/smoke_test.py` (Requisitos 7.5 y NFR-2, ADR 0009)."""

from __future__ import annotations

import math

import httpx
import pytest
from botocore.credentials import ReadOnlyCredentials
from botocore.exceptions import NoCredentialsError

from smoke_test import (
    DEFAULT_MAX_WAIT_S,
    DEFAULT_REQUEST_TIMEOUT_S,
    BotocoreSigV4Signer,
    SmokeTestConfig,
    SmokeTestError,
    main,
    run_smoke_test,
)

API_ENDPOINT = "https://abc1234567.execute-api.us-east-1.amazonaws.com"
TEST_CREDS = ReadOnlyCredentials(
    access_key="TESTKEY0000000000001",
    secret_key="test-only-synthetic-secret-value-not-real",  # noqa: S106
    token="test-only-synthetic-session-token-value",  # noqa: S106
)


class FakeClock:
    """Reloj determinista para probar reintentos y presupuesto NFR-2."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.req("fase-1a:7.5", "fase-1a:NFR-2")
def test_smoke_test_firma_sigv4_y_verifica_401_sin_filtrar_cabeceras() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/api/v1/me":
            return httpx.Response(401, json={"message": "Unauthorized"})
        raise AssertionError(f"Ruta inesperada: {request.url.path}")

    clock = FakeClock()
    logs: list[str] = []
    config = SmokeTestConfig(api_endpoint=API_ENDPOINT)
    assert config.request_timeout_s == DEFAULT_REQUEST_TIMEOUT_S
    assert config.request_timeout_s >= 40.0
    assert config.max_wait_s == DEFAULT_MAX_WAIT_S

    result = run_smoke_test(
        config,
        signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
        transport=httpx.MockTransport(handler),
        clock=clock,
        sleep=clock.sleep,
        log=logs.append,
    )

    assert result.ready_status == 200
    assert result.ready_attempts == 1
    assert result.unauth_status == 401
    assert result.within_nfr2_budget is True
    assert clock.sleeps == []

    assert len(seen_requests) == 2
    ready_req, me_req = seen_requests
    auth_header = ready_req.headers.get("authorization", "")
    assert auth_header.startswith("AWS4-HMAC-SHA256 ")
    assert "us-east-1/execute-api/aws4_request" in auth_header
    assert "x-amz-date" in ready_req.headers
    assert ready_req.headers.get("x-amz-security-token") == TEST_CREDS.token
    assert "authorization" not in me_req.headers

    joined_logs = "\n".join(logs)
    assert "TESTKEY0000000000001" not in joined_logs
    assert "synthetic-secret" not in joined_logs
    assert "synthetic-session-token" not in joined_logs
    assert "Unauthorized" not in joined_logs
    assert "abc1234567" not in joined_logs


@pytest.mark.req("fase-1a:7.5", "fase-1a:NFR-2")
def test_smoke_test_respeta_retry_after_y_reintenta_5xx_y_timeouts() -> None:
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/health/ready":
            attempts += 1
            clock.now += 10.0
            if attempts == 1:
                return httpx.Response(
                    503,
                    headers={"Retry-After": "7"},
                    json={"code": "DATABASE_UNAVAILABLE"},
                )
            if attempts == 2:
                return httpx.Response(503, json={"message": "Service Unavailable"})
            if attempts == 3:
                raise httpx.ReadTimeout("timeout simulado", request=request)
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/api/v1/me":
            return httpx.Response(401, json={"message": "Unauthorized"})
        raise AssertionError(f"Ruta inesperada: {request.url.path}")

    result = run_smoke_test(
        SmokeTestConfig(api_endpoint=API_ENDPOINT, max_wait_s=120.0),
        signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
        transport=httpx.MockTransport(handler),
        clock=clock,
        sleep=clock.sleep,
        log=lambda _: None,
    )

    assert result.ready_status == 200
    assert result.ready_attempts == 4
    assert result.unauth_status == 401
    assert clock.sleeps == [7.0, 5.0, 5.0]
    assert result.ready_elapsed_ms == 57_000
    assert result.within_nfr2_budget is True


@pytest.mark.req("fase-1a:7.5")
def test_smoke_test_acota_retry_after_extremos_y_no_finitos() -> None:
    clock = FakeClock()
    headers_seq = ["nan", "inf", "0", "999"]
    idx = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal idx
        if request.url.path == "/health/ready":
            if idx < len(headers_seq):
                hdr = headers_seq[idx]
                idx += 1
                return httpx.Response(503, headers={"Retry-After": hdr})
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(401)

    result = run_smoke_test(
        SmokeTestConfig(api_endpoint=API_ENDPOINT, max_wait_s=120.0),
        signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
        transport=httpx.MockTransport(handler),
        clock=clock,
        sleep=clock.sleep,
        log=lambda _: None,
    )

    assert result.ready_status == 200
    # nan -> fallback 5s, inf -> fallback 5s, 0 -> acotado a 1s, 999 -> acotado a 30s
    assert clock.sleeps == [5.0, 5.0, 1.0, 30.0]


@pytest.mark.req("fase-1a:7.5")
def test_smoke_test_falla_al_agotar_120_segundos() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            return httpx.Response(503, headers={"Retry-After": "30"})
        raise AssertionError("No debe llamar a /api/v1/me si /health/ready falló.")

    with pytest.raises(SmokeTestError, match="120 s"):
        run_smoke_test(
            SmokeTestConfig(api_endpoint=API_ENDPOINT, max_wait_s=120.0),
            signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
            transport=httpx.MockTransport(handler),
            clock=clock,
            sleep=clock.sleep,
            log=lambda _: None,
        )

    assert sum(clock.sleeps) == pytest.approx(120.0)


@pytest.mark.req("fase-1a:7.5")
def test_smoke_test_falla_sin_reintento_ante_403_iam_en_health_ready() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"message": "Forbidden"})

    clock = FakeClock()
    with pytest.raises(SmokeTestError, match="403"):
        run_smoke_test(
            SmokeTestConfig(api_endpoint=API_ENDPOINT),
            signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
            transport=httpx.MockTransport(handler),
            clock=clock,
            sleep=clock.sleep,
            log=lambda _: None,
        )

    assert calls == 1
    assert clock.sleeps == []


@pytest.mark.req("fase-1a:7.5")
@pytest.mark.parametrize("bad_status", [200, 403, 500])
def test_smoke_test_falla_si_me_sin_token_no_devuelve_401(bad_status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/api/v1/me":
            return httpx.Response(bad_status, json={"sub": "unexpected"})
        raise AssertionError("Ruta inesperada")

    with pytest.raises(SmokeTestError, match="401"):
        run_smoke_test(
            SmokeTestConfig(api_endpoint=API_ENDPOINT),
            signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
            transport=httpx.MockTransport(handler),
            clock=FakeClock(),
            sleep=lambda _: None,
            log=lambda _: None,
        )


def test_smoke_test_rechaza_http_sin_tls_urls_invalidas_y_floats_no_finitos() -> None:
    invalid_configs = [
        SmokeTestConfig(api_endpoint="http://abc.execute-api.us-east-1.amazonaws.com"),
        SmokeTestConfig(api_endpoint="https://"),
        SmokeTestConfig(api_endpoint="https://user:pass@example.com"),
        SmokeTestConfig(api_endpoint="https://example.com?foo=bar"),
        SmokeTestConfig(api_endpoint=API_ENDPOINT, max_wait_s=math.nan),
        SmokeTestConfig(api_endpoint=API_ENDPOINT, request_timeout_s=math.inf),
        SmokeTestConfig(api_endpoint=API_ENDPOINT, region="--bad-region"),
    ]
    for bad_cfg in invalid_configs:
        with pytest.raises(SmokeTestError):
            run_smoke_test(bad_cfg)


def test_smoke_test_envuelve_error_de_botocore_en_smoke_test_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingSession:
        def get_credentials(self) -> object:
            raise NoCredentialsError()

    monkeypatch.setattr("smoke_test.Session", FailingSession)

    with pytest.raises(SmokeTestError, match="credenciales"):
        run_smoke_test(
            SmokeTestConfig(api_endpoint=API_ENDPOINT),
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
            log=lambda _: None,
        )


def test_smoke_test_falla_si_ready_200_tiene_cuerpo_invalido() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    with pytest.raises(SmokeTestError, match="ready"):
        run_smoke_test(
            SmokeTestConfig(api_endpoint=API_ENDPOINT),
            signer=BotocoreSigV4Signer(region="us-east-1", credentials=TEST_CREDS),
            transport=httpx.MockTransport(handler),
            clock=FakeClock(),
            sleep=lambda _: None,
            log=lambda _: None,
        )


def test_smoke_test_cli_devuelve_1_con_endpoint_invalido() -> None:
    assert main(["--api-endpoint", "not-a-url"]) == 1
