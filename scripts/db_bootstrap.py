"""Bootstrap SQL idempotente por RDS Data API (ADR 0007, D3, Requisitos 5.3 y 7.4).

Ejecuta `scripts/sql/bootstrap.sql` (un único bloque `DO $$ ... $$`) mediante
`aws rds-data execute-statement` con `--continue-after-timeout` y reintenta con
espera exponencial hasta 120 s ante `DatabaseResumingException` y
`DatabaseUnavailableException`. Nunca imprime ARNs de secretos ni credenciales.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from runner import Runner, SubprocessRunner

DEFAULT_REGION = "us-east-1"
DEFAULT_DATABASE = "monitorglucosa"
DEFAULT_MAX_WAIT_S = 120.0
DEFAULT_INITIAL_DELAY_S = 2.0
DEFAULT_MAX_DELAY_S = 15.0
DATA_API_MAX_SQL_CHARS = 65_536

REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z]+)+-\d+$")
CLUSTER_ARN_PATTERN = re.compile(
    r"^arn:aws:rds:[a-z0-9-]+:\d{12}:cluster:[A-Za-z0-9-]+$"
)
SECRET_ARN_PATTERN = re.compile(
    r"^arn:aws:secretsmanager:[a-z0-9-]+:\d{12}:secret:[A-Za-z0-9/_+=.@!-]+$"
)
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

RETRYABLE_ERROR_CODES: tuple[str, ...] = (
    "DatabaseResumingException",
    "DatabaseUnavailableException",
)

DEFAULT_SQL_PATH = Path(__file__).resolve().parent / "sql" / "bootstrap.sql"


class BootstrapError(RuntimeError):
    """Error no recuperable o presupuesto agotado durante el bootstrap SQL."""


@dataclass(frozen=True)
class BootstrapConfig:
    """Parámetros validados para ejecutar el bootstrap SQL por RDS Data API."""

    cluster_arn: str
    secret_arn: str
    database: str = DEFAULT_DATABASE
    region: str = DEFAULT_REGION
    sql_path: Path = DEFAULT_SQL_PATH
    max_wait_s: float = DEFAULT_MAX_WAIT_S
    initial_delay_s: float = DEFAULT_INITIAL_DELAY_S
    max_delay_s: float = DEFAULT_MAX_DELAY_S


@dataclass(frozen=True)
class BootstrapResult:
    """Resumen seguro del resultado del bootstrap SQL."""

    attempts: int
    elapsed_ms: int


def _validate_config(config: BootstrapConfig) -> str:
    """Valida parámetros estrictamente y devuelve el SQL listo para Data API."""
    if not CLUSTER_ARN_PATTERN.match(config.cluster_arn.strip()):
        raise BootstrapError("cluster_arn debe ser un ARN válido de clúster RDS.")
    if not SECRET_ARN_PATTERN.match(config.secret_arn.strip()):
        raise BootstrapError("secret_arn debe ser un ARN válido de Secrets Manager.")
    if not DATABASE_NAME_PATTERN.match(config.database.strip()):
        raise BootstrapError("database no es un identificador PostgreSQL válido.")
    if not REGION_PATTERN.match(config.region.strip()):
        raise BootstrapError("region no es una región de AWS válida.")
    if not math.isfinite(config.max_wait_s) or config.max_wait_s < 0:
        raise BootstrapError("max_wait_s debe ser un número finito mayor o igual a 0.")
    if (
        not math.isfinite(config.initial_delay_s)
        or not math.isfinite(config.max_delay_s)
        or config.initial_delay_s <= 0
        or config.max_delay_s <= 0
    ):
        raise BootstrapError("Los tiempos de espera deben ser finitos y positivos.")
    if not config.sql_path.is_file():
        raise BootstrapError(
            f"No existe el archivo SQL de bootstrap: {config.sql_path.name}"
        )

    sql_text = config.sql_path.read_text(encoding="utf-8").strip()
    if not sql_text:
        raise BootstrapError("El archivo SQL de bootstrap está vacío.")
    if len(sql_text) > DATA_API_MAX_SQL_CHARS:
        raise BootstrapError(
            "El SQL de bootstrap supera el límite de RDS Data API "
            f"({DATA_API_MAX_SQL_CHARS} caracteres)."
        )
    return sql_text


def _detect_retryable_error(stdout: str, stderr: str) -> str | None:
    """Devuelve el código de error reintentable si Aurora está reanudando."""
    combined = f"{stderr}\n{stdout}"
    for code in RETRYABLE_ERROR_CODES:
        if code in combined:
            return code
    return None


def _classify_fatal_error(stdout: str, stderr: str) -> str:
    """Identifica el código conocido de error sin exponer ARNs ni detalles crudos."""
    combined = f"{stderr}\n{stdout}"
    known_codes = (
        "DatabaseErrorException",
        "SecretsErrorException",
        "AccessDeniedException",
        "BadRequestException",
        "ForbiddenException",
        "StatementTimeoutException",
        "InternalServerErrorException",
    )
    for code in known_codes:
        if code in combined:
            return code
    return "AwsCliError"


def build_execute_statement_command(
    config: BootstrapConfig,
    sql_text: str,
) -> list[str]:
    """Construye `aws rds-data execute-statement` usando `--sql=...` (sin shell).

    Unir `--sql=` evita que AWS CLI v2 interprete el comentario SQL inicial (`-- `)
    como un flag independiente de `argparse`.
    """
    return [
        "aws",
        "rds-data",
        "execute-statement",
        f"--region={config.region.strip()}",
        f"--resource-arn={config.cluster_arn.strip()}",
        f"--secret-arn={config.secret_arn.strip()}",
        f"--database={config.database.strip()}",
        f"--sql={sql_text}",
        "--continue-after-timeout",
        "--output=json",
    ]


def run_bootstrap(
    config: BootstrapConfig,
    *,
    runner: Runner | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> BootstrapResult:
    """Ejecuta `bootstrap.sql` por RDS Data API con reintentos exponenciales."""
    sql_text = _validate_config(config)
    active_runner = runner or SubprocessRunner()
    emit = log or (lambda msg: print(msg, flush=True))

    command = build_execute_statement_command(config, sql_text)
    started = clock()
    deadline = started + config.max_wait_s
    delay = config.initial_delay_s
    attempts = 0

    while True:
        attempts += 1
        result = active_runner.run(command)
        elapsed_ms = int((clock() - started) * 1000)

        if result.returncode == 0:
            emit(f"[db_bootstrap] ok intento={attempts} duracion_ms={elapsed_ms}")
            return BootstrapResult(attempts=attempts, elapsed_ms=elapsed_ms)

        retryable_code = _detect_retryable_error(result.stdout, result.stderr)
        if retryable_code is None:
            fatal_code = _classify_fatal_error(result.stdout, result.stderr)
            emit(
                f"[db_bootstrap] fallo_no_reintentable intento={attempts} "
                f"codigo={fatal_code} duracion_ms={elapsed_ms}"
            )
            raise BootstrapError(
                f"Bootstrap SQL falló sin reintento ({fatal_code}) "
                f"en el intento {attempts}."
            )

        remaining = deadline - clock()
        if remaining <= 0:
            emit(
                f"[db_bootstrap] presupuesto_agotado intentos={attempts} "
                f"ultimo_codigo={retryable_code} duracion_ms={elapsed_ms}"
            )
            raise BootstrapError(
                f"Bootstrap SQL agotó el presupuesto de {config.max_wait_s:.0f} s "
                f"tras {attempts} intentos ({retryable_code})."
            )

        wait_s = min(delay, remaining)
        emit(
            f"[db_bootstrap] reintento intento={attempts} codigo={retryable_code} "
            f"espera_s={wait_s:.1f}"
        )
        sleep(wait_s)
        delay = min(delay * 2.0, config.max_delay_s)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta scripts/sql/bootstrap.sql por RDS Data API con reintentos."
    )
    parser.add_argument(
        "--cluster-arn",
        default=os.environ.get("CLUSTER_ARN", ""),
        help="ARN del clúster Aurora (o env CLUSTER_ARN).",
    )
    parser.add_argument(
        "--secret-arn",
        default=os.environ.get("MASTER_SECRET_ARN", ""),
        help="ARN del secreto maestro gestionado por RDS (o env MASTER_SECRET_ARN).",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("DATABASE_NAME", DEFAULT_DATABASE),
        help=f"Nombre de la base de datos (por defecto: {DEFAULT_DATABASE}).",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"Región de AWS (por defecto: {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=DEFAULT_SQL_PATH,
        help="Ruta al archivo SQL idempotente de bootstrap.",
    )
    parser.add_argument(
        "--max-wait-s",
        type=float,
        default=DEFAULT_MAX_WAIT_S,
        help=(
            "Presupuesto máximo de reintentos en segundos "
            f"(por defecto: {DEFAULT_MAX_WAIT_S})."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada CLI."""
    args = _parse_args(argv)
    config = BootstrapConfig(
        cluster_arn=args.cluster_arn,
        secret_arn=args.secret_arn,
        database=args.database,
        region=args.region,
        sql_path=args.sql_file,
        max_wait_s=args.max_wait_s,
    )
    try:
        run_bootstrap(config)
    except BootstrapError as exc:
        print(f"[db_bootstrap] ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
