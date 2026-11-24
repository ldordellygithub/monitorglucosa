"""Pruebas unitarias de `scripts/db_bootstrap.py` con dobles de CLI de AWS."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from db_bootstrap import (
    DATA_API_MAX_SQL_CHARS,
    DEFAULT_SQL_PATH,
    BootstrapConfig,
    BootstrapError,
    main,
    run_bootstrap,
)
from runner import CommandResult

CLUSTER_ARN = "arn:aws:rds:us-east-1:111122223333:cluster:monitorglucosa"
MASTER_ARN = "arn:aws:secretsmanager:us-east-1:111122223333:secret:rds!cluster-abc123"
SECRET_ARN = MASTER_ARN


class FakeClock:
    """Reloj determinista para probar reintentos sin esperar tiempo real."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class SequenceRunner:
    """Doble de `Runner` que devuelve una secuencia de `CommandResult`."""

    def __init__(self, responses: Sequence[CommandResult]) -> None:
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        del cwd, env, timeout_s
        self.calls.append(list(command))
        if not self._responses:
            raise AssertionError("Se recibieron más llamadas de las configuradas.")
        return self._responses.pop(0)


@pytest.mark.req("fase-1a:5.3", "fase-1a:7.4")
def test_bootstrap_ejecuta_data_api_con_continue_after_timeout_y_sql_real() -> None:
    runner = SequenceRunner([CommandResult(returncode=0, stdout='{"records": []}')])
    clock = FakeClock()
    logs: list[str] = []

    result = run_bootstrap(
        BootstrapConfig(cluster_arn=CLUSTER_ARN, secret_arn=SECRET_ARN),
        runner=runner,
        clock=clock,
        sleep=clock.sleep,
        log=logs.append,
    )

    assert result.attempts == 1
    assert clock.sleeps == []
    assert len(runner.calls) == 1
    cmd = runner.calls[0]
    expected_sql = DEFAULT_SQL_PATH.read_text(encoding="utf-8").strip()
    assert cmd[:3] == ["aws", "rds-data", "execute-statement"]
    assert "--continue-after-timeout" in cmd
    assert "--region=us-east-1" in cmd
    assert f"--resource-arn={CLUSTER_ARN}" in cmd
    assert f"--secret-arn={SECRET_ARN}" in cmd
    assert "--database=monitorglucosa" in cmd
    # --sql= unido con '=' evita que AWS CLI v2 confunda el '-- ' inicial del SQL.
    assert f"--sql={expected_sql}" in cmd
    assert "--output=json" in cmd
    assert all(SECRET_ARN not in line and CLUSTER_ARN not in line for line in logs)


@pytest.mark.req("fase-1a:7.4")
def test_bootstrap_reintenta_exponencialmente_ante_aurora_reanudando() -> None:
    runner = SequenceRunner(
        [
            CommandResult(
                returncode=254,
                stderr=(
                    "An error occurred (DatabaseResumingException) "
                    "when calling ExecuteStatement"
                ),
            ),
            CommandResult(
                returncode=254,
                stderr="An error occurred (DatabaseUnavailableException)",
            ),
            CommandResult(returncode=0, stdout="{}"),
        ]
    )
    clock = FakeClock()
    logs: list[str] = []

    result = run_bootstrap(
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn=SECRET_ARN,
            max_wait_s=120.0,
            initial_delay_s=2.0,
            max_delay_s=15.0,
        ),
        runner=runner,
        clock=clock,
        sleep=clock.sleep,
        log=logs.append,
    )

    assert result.attempts == 3
    assert clock.sleeps == [2.0, 4.0]
    assert any("DatabaseResumingException" in line for line in logs)
    assert any("DatabaseUnavailableException" in line for line in logs)
    assert all(SECRET_ARN not in line and "111122223333" not in line for line in logs)


@pytest.mark.req("fase-1a:7.4")
def test_bootstrap_agota_presupuesto_de_120_segundos_sin_excederlo() -> None:
    resuming = CommandResult(returncode=254, stderr="DatabaseResumingException")
    runner = SequenceRunner([resuming] * 20)
    clock = FakeClock()

    with pytest.raises(BootstrapError, match="120 s"):
        run_bootstrap(
            BootstrapConfig(
                cluster_arn=CLUSTER_ARN,
                secret_arn=SECRET_ARN,
                max_wait_s=120.0,
                initial_delay_s=2.0,
                max_delay_s=15.0,
            ),
            runner=runner,
            clock=clock,
            sleep=clock.sleep,
            log=lambda _: None,
        )

    assert sum(clock.sleeps) == pytest.approx(120.0)
    assert clock.now == pytest.approx(120.0)
    assert clock.sleeps[:4] == [2.0, 4.0, 8.0, 15.0]


@pytest.mark.req("fase-1a:7.4")
@pytest.mark.parametrize(
    "error_code",
    ["DatabaseErrorException", "SecretsErrorException", "AccessDeniedException"],
)
def test_bootstrap_falla_sin_reintento_ante_errores_no_recuperables(
    error_code: str,
) -> None:
    runner = SequenceRunner(
        [
            CommandResult(
                returncode=254,
                stderr=f"An error occurred ({error_code}): secret={SECRET_ARN}",
            )
        ]
    )
    clock = FakeClock()
    logs: list[str] = []

    with pytest.raises(BootstrapError) as exc_info:
        run_bootstrap(
            BootstrapConfig(cluster_arn=CLUSTER_ARN, secret_arn=SECRET_ARN),
            runner=runner,
            clock=clock,
            sleep=clock.sleep,
            log=logs.append,
        )

    assert len(runner.calls) == 1
    assert clock.sleeps == []
    assert error_code in str(exc_info.value)
    assert SECRET_ARN not in str(exc_info.value)
    assert all(SECRET_ARN not in line for line in logs)


def test_bootstrap_valida_parametros_argumentos_cli_y_tamano_de_sql(
    tmp_path: Path,
) -> None:
    oversized_sql = tmp_path / "big.sql"
    oversized_sql.write_text("x" * (DATA_API_MAX_SQL_CHARS + 1), encoding="utf-8")

    with pytest.raises(BootstrapError, match="65536"):
        run_bootstrap(
            BootstrapConfig(
                cluster_arn=CLUSTER_ARN,
                secret_arn=SECRET_ARN,
                sql_path=oversized_sql,
            ),
            runner=SequenceRunner([]),
        )

    invalid_configs = [
        BootstrapConfig(cluster_arn="--inject", secret_arn=SECRET_ARN),
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn="file:///etc/passwd",  # noqa: S106
        ),
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn=SECRET_ARN,
            region="--debug",
        ),
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn=SECRET_ARN,
            database="-bad-db",
        ),
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn=SECRET_ARN,
            max_wait_s=math.nan,
        ),
        BootstrapConfig(
            cluster_arn=CLUSTER_ARN,
            secret_arn=SECRET_ARN,
            initial_delay_s=math.inf,
        ),
    ]
    for bad_cfg in invalid_configs:
        with pytest.raises(BootstrapError):
            run_bootstrap(bad_cfg, runner=SequenceRunner([]))


def test_bootstrap_cli_devuelve_1_si_faltan_parametros() -> None:
    assert main(["--cluster-arn", "", "--secret-arn", ""]) == 1
