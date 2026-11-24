"""Orquestador de despliegue en dos fases con vuelta atrás (Requisitos 7.4, 7.5, NFR-5).

Secuencia (design.md · D2, D3, D4, D5 y Property 6):
1. Obtiene el ID de cuenta de AWS y lo enmascara con `::add-mask::`.
2. Lee `api_image_digest` actual de Terraform (`D_prev`, vacío en primer despliegue).
3. Si existe `D_prev`, verifica en ECR (`describe-images`) que sigue presente.
4. Fase 1: aplica infraestructura con `migrator = D_new` y `api = D_prev` (o `D_new`
   en el primer despliegue), escribiendo solo el resumen redactado del plan/apply.
5. Ejecuta `db_bootstrap.py` (bootstrap SQL idempotente por RDS Data API, hasta 120 s).
6. Espera `aws lambda wait function-active-v2` del `migrator` y lo invoca síncronamente
   con `--cli-read-timeout 310`; exige ausencia de `FunctionError` y `status == "ok"`.
7. Fase 2: si `D_prev` existe y difiere de `D_new`, promueve `api = D_new`.
8. Ejecuta `smoke_test.py` (`/health/ready` SigV4 hasta 120 s + `/api/v1/me` → 401).
   Si falla y existe `D_prev`, aplica vuelta atrás a `api = D_prev` y falla.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from db_bootstrap import (
    DATABASE_NAME_PATTERN,
    DEFAULT_DATABASE,
    DEFAULT_REGION,
    DEFAULT_SQL_PATH,
    REGION_PATTERN,
    BootstrapConfig,
    BootstrapError,
    BootstrapResult,
    run_bootstrap,
)
from db_bootstrap import (
    DEFAULT_MAX_WAIT_S as DEFAULT_BOOTSTRAP_MAX_WAIT_S,
)
from runner import Runner, SubprocessRunner
from smoke_test import (
    DEFAULT_MAX_WAIT_S as DEFAULT_SMOKE_MAX_WAIT_S,
)
from smoke_test import (
    DEFAULT_REQUEST_TIMEOUT_S as DEFAULT_SMOKE_TIMEOUT_S,
)
from smoke_test import (
    SmokeTestConfig,
    SmokeTestError,
    SmokeTestResult,
    run_smoke_test,
)

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ACCOUNT_ID_PATTERN = re.compile(r"^\d{12}$")
ECR_REPO_PATTERN = re.compile(r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$")
LAMBDA_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REVISION_PATTERN = re.compile(r"^[0-9A-Za-z_.-]{1,64}$")

SUMMARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Plan: \d+ to add, \d+ to change, \d+ to destroy\.$"),
    re.compile(r"^Apply complete! Resources: \d+ added, \d+ changed, \d+ destroyed\.$"),
    re.compile(r"^No changes\. Your infrastructure matches the configuration\.$"),
)

DEFAULT_TERRAFORM_DIR = Path(__file__).resolve().parent.parent / "infra" / "terraform"
DEFAULT_ECR_REPOSITORY = "monitorglucosa-api"
DEFAULT_MIGRATOR_FUNCTION = "monitorglucosa-migrator"
DEFAULT_MIGRATOR_READ_TIMEOUT_S = 310


class DeployError(RuntimeError):
    """Error controlado durante el despliegue en dos fases."""

    def __init__(
        self,
        message: str,
        *,
        step: str,
        active_digest: str | None,
        rolled_back: bool = False,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.active_digest = active_digest
        self.rolled_back = rolled_back


@dataclass(frozen=True)
class DeployConfig:
    """Parámetros validados para orquestar el despliegue."""

    new_digest: str
    terraform_dir: Path = DEFAULT_TERRAFORM_DIR
    ecr_repository: str = DEFAULT_ECR_REPOSITORY
    migrator_function_name: str = DEFAULT_MIGRATOR_FUNCTION
    database_name: str = DEFAULT_DATABASE
    region: str = DEFAULT_REGION
    bootstrap_sql_path: Path = DEFAULT_SQL_PATH
    bootstrap_max_wait_s: float = DEFAULT_BOOTSTRAP_MAX_WAIT_S
    smoke_max_wait_s: float = DEFAULT_SMOKE_MAX_WAIT_S
    smoke_request_timeout_s: float = DEFAULT_SMOKE_TIMEOUT_S
    migrator_read_timeout_s: int = DEFAULT_MIGRATOR_READ_TIMEOUT_S


@dataclass(frozen=True)
class TerraformOutputs:
    """Salidas mínimas de Terraform necesarias para el despliegue."""

    cluster_arn: str
    master_secret_arn: str
    api_endpoint: str


@dataclass(frozen=True)
class DeployResult:
    """Resumen seguro del despliegue exitoso."""

    previous_digest: str | None
    deployed_digest: str
    migration_revision: str | None
    bootstrap_result: BootstrapResult
    smoke_result: SmokeTestResult


BootstrapCallable = Callable[[BootstrapConfig, Runner], BootstrapResult]
SmokeCallable = Callable[[SmokeTestConfig], SmokeTestResult]


class _LogRedactor:
    """Enmascara valores sensibles en Actions y los censura en cualquier log local."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._secrets: list[str] = []

    def add_mask(self, value: str) -> None:
        for part in value.splitlines():
            cleaned = part.strip()
            if not cleaned or "\r" in cleaned or cleaned in self._secrets:
                continue
            self._secrets.append(cleaned)
            self._emit(f"::add-mask::{cleaned}")

    def log(self, message: str) -> None:
        sanitized = message.replace("\r", " ").replace("\n", " ")
        for secret in self._secrets:
            sanitized = sanitized.replace(secret, "***")
        self._emit(sanitized)


def _validate_config(config: DeployConfig) -> tuple[str, str, str, str, str]:
    """Valida todos los parámetros externos antes de invocar AWS o Terraform."""
    new_digest = config.new_digest.strip()
    if not DIGEST_PATTERN.match(new_digest):
        raise DeployError(
            "El digest D_new debe cumplir sha256:<64 hex minúsculas>.",
            step="validate",
            active_digest=None,
        )
    region = config.region.strip()
    if not REGION_PATTERN.match(region):
        raise DeployError(
            "La región de AWS no tiene un formato válido.",
            step="validate",
            active_digest=None,
        )
    ecr_repository = config.ecr_repository.strip()
    if not ECR_REPO_PATTERN.match(ecr_repository):
        raise DeployError(
            "El nombre del repositorio ECR no tiene un formato válido.",
            step="validate",
            active_digest=None,
        )
    migrator_fn = config.migrator_function_name.strip()
    if not LAMBDA_NAME_PATTERN.match(migrator_fn):
        raise DeployError(
            "El nombre de la función Lambda migrator no tiene un formato válido.",
            step="validate",
            active_digest=None,
        )
    database_name = config.database_name.strip()
    if not DATABASE_NAME_PATTERN.match(database_name):
        raise DeployError(
            "El nombre de base de datos no es un identificador PostgreSQL válido.",
            step="validate",
            active_digest=None,
        )
    if config.migrator_read_timeout_s <= 0:
        raise DeployError(
            "migrator_read_timeout_s debe ser mayor que 0.",
            step="validate",
            active_digest=None,
        )
    return new_digest, region, ecr_repository, migrator_fn, database_name


def _extract_terraform_summary(stdout: str) -> list[str]:
    """Devuelve solo líneas exactas de resumen de plan/apply (ADR 0008)."""
    summary_lines: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if any(pattern.match(line) for pattern in SUMMARY_PATTERNS):
            summary_lines.append(line)
    return summary_lines


def _mask_account_id(runner: Runner, region: str, redactor: _LogRedactor) -> str:
    """Obtiene el ID de cuenta por STS y falla cerrado si no puede enmascararlo."""
    result = runner.run(
        [
            "aws",
            "sts",
            "get-caller-identity",
            f"--region={region}",
            "--query=Account",
            "--output=text",
        ]
    )
    if result.returncode != 0:
        raise DeployError(
            "No se pudo obtener la identidad de AWS (aws sts get-caller-identity).",
            step="sts",
            active_digest=None,
        )
    account_id = result.stdout.strip()
    if not ACCOUNT_ID_PATTERN.match(account_id):
        raise DeployError(
            "STS no devolvió un ID de cuenta AWS válido de 12 dígitos.",
            step="sts",
            active_digest=None,
        )
    redactor.add_mask(account_id)
    return account_id


def _is_missing_output_error(stderr: str, stdout: str) -> bool:
    """Detecta solo los mensajes exactos de Terraform cuando falta el output."""
    combined = f"{stderr}\n{stdout}".lower()
    markers = (
        "no outputs found",
        "the state file either has no outputs",
        'output "api_image_digest" not found',
        "the output variable requested could not be found",
    )
    return any(marker in combined for marker in markers)


def _read_previous_digest(runner: Runner, terraform_dir: Path) -> str | None:
    """Lee `api_image_digest` actual de Terraform (None en primer despliegue)."""
    result = runner.run(
        ["terraform", "output", "-raw", "-no-color", "api_image_digest"],
        cwd=terraform_dir,
    )
    if result.returncode != 0:
        if _is_missing_output_error(result.stderr, result.stdout):
            return None
        raise DeployError(
            "No se pudo leer el digest anterior (api_image_digest) de Terraform.",
            step="read_d_prev",
            active_digest=None,
        )

    raw_digest = result.stdout.strip()
    if not raw_digest:
        return None
    if not DIGEST_PATTERN.match(raw_digest):
        raise DeployError(
            "El output api_image_digest de Terraform no tiene un digest sha256 válido.",
            step="read_d_prev",
            active_digest=None,
        )
    return raw_digest


def _verify_digest_in_ecr(
    runner: Runner,
    *,
    region: str,
    repository: str,
    digest: str,
) -> None:
    """Comprueba que `D_prev` sigue existiendo en ECR antes de modificar nada (D5)."""
    result = runner.run(
        [
            "aws",
            "ecr",
            "describe-images",
            f"--region={region}",
            f"--repository-name={repository}",
            f"--image-ids=imageDigest={digest}",
            "--output=json",
        ]
    )
    if result.returncode != 0:
        raise DeployError(
            "El digest anterior D_prev ya no existe en ECR; "
            "despliegue detenido sin cambios.",
            step="ecr_check",
            active_digest=digest,
        )


def _terraform_apply(
    runner: Runner,
    *,
    terraform_dir: Path,
    api_digest: str,
    migrator_digest: str,
    phase_label: str,
    redactor: _LogRedactor,
    active_digest_on_failure: str | None,
) -> None:
    """Ejecuta `terraform apply` y registra únicamente el resumen redactado."""
    result = runner.run(
        [
            "terraform",
            "apply",
            "-auto-approve",
            "-input=false",
            "-no-color",
            f"-var=api_image_digest={api_digest}",
            f"-var=migrator_image_digest={migrator_digest}",
        ],
        cwd=terraform_dir,
    )
    for line in _extract_terraform_summary(result.stdout):
        redactor.log(f"[deploy:{phase_label}] {line}")

    if result.returncode != 0:
        raise DeployError(
            f"terraform apply falló en {phase_label}.",
            step=phase_label,
            active_digest=active_digest_on_failure,
        )


def _read_terraform_outputs(
    runner: Runner,
    *,
    terraform_dir: Path,
    redactor: _LogRedactor,
    active_digest_on_failure: str | None,
) -> TerraformOutputs:
    """Lee las salidas necesarias de Terraform y enmascara valores sensibles."""
    result = runner.run(
        ["terraform", "output", "-json", "-no-color"],
        cwd=terraform_dir,
    )
    if result.returncode != 0:
        raise DeployError(
            "No se pudieron leer las salidas de Terraform tras la fase 1.",
            step="terraform_outputs",
            active_digest=active_digest_on_failure,
        )

    try:
        parsed: Any = json.loads(result.stdout)
    except ValueError as exc:
        raise DeployError(
            "Las salidas JSON de Terraform no son válidas.",
            step="terraform_outputs",
            active_digest=active_digest_on_failure,
        ) from exc

    if not isinstance(parsed, dict):
        raise DeployError(
            "Las salidas de Terraform deben ser un objeto JSON.",
            step="terraform_outputs",
            active_digest=active_digest_on_failure,
        )

    def _extract(key: str) -> str:
        entry = parsed.get(key)
        raw_value: object = entry.get("value") if isinstance(entry, dict) else None
        if not isinstance(raw_value, str):
            raise DeployError(
                f"Falta la salida obligatoria de Terraform: {key}.",
                step="terraform_outputs",
                active_digest=active_digest_on_failure,
            )
        value = raw_value.strip()
        if not value:
            raise DeployError(
                f"La salida de Terraform {key} está vacía.",
                step="terraform_outputs",
                active_digest=active_digest_on_failure,
            )
        return value

    cluster_arn = _extract("cluster_arn")
    master_secret_arn = _extract("master_secret_arn")
    api_endpoint = _extract("api_endpoint")

    redactor.add_mask(master_secret_arn)
    redactor.add_mask(cluster_arn)
    redactor.add_mask(api_endpoint)
    endpoint_host = urlsplit(api_endpoint).hostname
    if endpoint_host:
        redactor.add_mask(endpoint_host)

    return TerraformOutputs(
        cluster_arn=cluster_arn,
        master_secret_arn=master_secret_arn,
        api_endpoint=api_endpoint,
    )


def _wait_and_invoke_migrator(
    runner: Runner,
    *,
    region: str,
    function_name: str,
    read_timeout_s: int,
    redactor: _LogRedactor,
    active_digest_on_failure: str | None,
) -> str | None:
    """Espera `function-active-v2` e invoca la Lambda `migrator` (D2, 7.4)."""
    wait_result = runner.run(
        [
            "aws",
            "lambda",
            "wait",
            "function-active-v2",
            f"--region={region}",
            f"--function-name={function_name}",
        ]
    )
    if wait_result.returncode != 0:
        raise DeployError(
            "La Lambda migrator no alcanzó el estado Active (function-active-v2).",
            step="migrator_wait",
            active_digest=active_digest_on_failure,
        )
    redactor.log("[deploy:migrator] function-active-v2 ok")

    with tempfile.TemporaryDirectory(prefix="mg-migrator-") as tmp_dir:
        response_file = Path(tmp_dir) / "response.json"
        invoke_result = runner.run(
            [
                "aws",
                "lambda",
                "invoke",
                f"--region={region}",
                f"--function-name={function_name}",
                f"--cli-read-timeout={read_timeout_s}",
                "--payload={}",
                "--cli-binary-format=raw-in-base64-out",
                "--output=json",
                str(response_file),
            ]
        )
        if invoke_result.returncode != 0:
            raise DeployError(
                "Falló la invocación síncrona de la Lambda migrator.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )

        if not invoke_result.stdout.strip():
            raise DeployError(
                "La invocación de Lambda migrator no devolvió metadatos JSON.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )

        try:
            meta: Any = json.loads(invoke_result.stdout)
        except ValueError as exc:
            raise DeployError(
                "Los metadatos de invocación de migrator no son JSON válidos.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            ) from exc

        if not isinstance(meta, dict):
            raise DeployError(
                "Los metadatos de invocación de migrator deben ser un objeto JSON.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )
        if meta.get("FunctionError"):
            raise DeployError(
                "La Lambda migrator terminó con FunctionError.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )
        status_code = meta.get("StatusCode")
        if type(status_code) is not int or status_code != 200:
            raise DeployError(
                "La invocación de migrator no devolvió StatusCode entero 200.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )

        if not response_file.is_file():
            raise DeployError(
                "La Lambda migrator no escribió archivo de respuesta.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            )

        try:
            payload: Any = json.loads(response_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise DeployError(
                "La respuesta de la Lambda migrator no es JSON válido.",
                step="migrator_invoke",
                active_digest=active_digest_on_failure,
            ) from exc

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise DeployError(
            "La migración no devolvió status='ok'; "
            "la API permanece en el digest anterior.",
            step="migrator_invoke",
            active_digest=active_digest_on_failure,
        )

    raw_revision = payload.get("revision")
    revision_str: str | None = None
    if isinstance(raw_revision, str) and REVISION_PATTERN.match(raw_revision):
        revision_str = raw_revision
    redactor.log(f"[deploy:migrator] ok revision={revision_str or 'none'}")
    return revision_str


def run_deploy(
    config: DeployConfig,
    *,
    runner: Runner | None = None,
    bootstrap_fn: BootstrapCallable | None = None,
    smoke_fn: SmokeCallable | None = None,
    log: Callable[[str], None] | None = None,
) -> DeployResult:
    """Orquesta el despliegue completo en dos fases con rollback automático."""
    new_digest, region, ecr_repository, migrator_fn, database_name = _validate_config(
        config
    )
    active_runner = runner or SubprocessRunner()
    emit = log or (lambda msg: print(msg, flush=True))
    redactor = _LogRedactor(emit)

    # 1. Identidad y enmascaramiento obligatorio del ID de cuenta (D4 / ADR 0008).
    _mask_account_id(active_runner, region, redactor)

    # 2. Lectura del digest anterior en servicio (D_prev).
    d_prev = _read_previous_digest(active_runner, config.terraform_dir)
    redactor.log(
        f"[deploy] inicio primer_despliegue={'si' if d_prev is None else 'no'}"
    )

    # 3. Verificación previa en ECR para garantizar que D_prev sigue disponible (D5).
    if d_prev is not None:
        _verify_digest_in_ecr(
            active_runner,
            region=region,
            repository=ecr_repository,
            digest=d_prev,
        )
        redactor.log("[deploy] verificacion ECR de D_prev ok")

    # 4. Fase 1: infra + migrator = D_new; api mantiene D_prev (o D_new si es primero).
    phase1_api_digest = d_prev if d_prev is not None else new_digest
    _terraform_apply(
        active_runner,
        terraform_dir=config.terraform_dir,
        api_digest=phase1_api_digest,
        migrator_digest=new_digest,
        phase_label="fase_1",
        redactor=redactor,
        active_digest_on_failure=d_prev,
    )

    outputs = _read_terraform_outputs(
        active_runner,
        terraform_dir=config.terraform_dir,
        redactor=redactor,
        active_digest_on_failure=phase1_api_digest,
    )

    # 5. Bootstrap SQL idempotente por RDS Data API (D3 / ADR 0007).
    bootstrap_config = BootstrapConfig(
        cluster_arn=outputs.cluster_arn,
        secret_arn=outputs.master_secret_arn,
        database=database_name,
        region=region,
        sql_path=config.bootstrap_sql_path,
        max_wait_s=config.bootstrap_max_wait_s,
    )
    try:
        if bootstrap_fn is not None:
            bootstrap_result = bootstrap_fn(bootstrap_config, active_runner)
        else:
            bootstrap_result = run_bootstrap(
                bootstrap_config,
                runner=active_runner,
                log=redactor.log,
            )
    except BootstrapError as exc:
        raise DeployError(
            f"Falló el bootstrap SQL: {exc}",
            step="bootstrap",
            active_digest=phase1_api_digest,
        ) from exc

    # 6. Espera function-active-v2 e invocación síncrona de Lambda migrator (D2 / 7.4).
    migration_revision = _wait_and_invoke_migrator(
        active_runner,
        region=region,
        function_name=migrator_fn,
        read_timeout_s=config.migrator_read_timeout_s,
        redactor=redactor,
        active_digest_on_failure=phase1_api_digest,
    )

    # 7. Fase 2: promover la API a D_new solo tras migración exitosa.
    if d_prev is not None and d_prev != new_digest:
        _terraform_apply(
            active_runner,
            terraform_dir=config.terraform_dir,
            api_digest=new_digest,
            migrator_digest=new_digest,
            phase_label="fase_2",
            redactor=redactor,
            active_digest_on_failure=d_prev,
        )

    # 8. Prueba de humo post-despliegue + vuelta atrás automática a D_prev si falla.
    smoke_config = SmokeTestConfig(
        api_endpoint=outputs.api_endpoint,
        region=region,
        max_wait_s=config.smoke_max_wait_s,
        request_timeout_s=config.smoke_request_timeout_s,
    )
    try:
        if smoke_fn is not None:
            smoke_result = smoke_fn(smoke_config)
        else:
            smoke_result = run_smoke_test(smoke_config, log=redactor.log)
    except SmokeTestError as exc:
        if d_prev is not None:
            redactor.log(
                "[deploy:rollback] prueba de humo fallida; "
                "iniciando vuelta atrás a D_prev"
            )
            try:
                _terraform_apply(
                    active_runner,
                    terraform_dir=config.terraform_dir,
                    api_digest=d_prev,
                    migrator_digest=new_digest,
                    phase_label="rollback",
                    redactor=redactor,
                    active_digest_on_failure=new_digest,
                )
            except DeployError as rollback_exc:
                raise DeployError(
                    f"Falló la prueba de humo ({exc}) y también falló la vuelta atrás.",
                    step="rollback",
                    active_digest=new_digest,
                    rolled_back=False,
                ) from rollback_exc

            redactor.log("[deploy:rollback] vuelta atrás a D_prev completada")
            raise DeployError(
                f"Prueba de humo fallida ({exc}); API revertida a D_prev.",
                step="smoke",
                active_digest=d_prev,
                rolled_back=True,
            ) from exc

        redactor.log(
            "[deploy] prueba de humo fallida en primer despliegue "
            "(sin D_prev para vuelta atrás)"
        )
        raise DeployError(
            f"Prueba de humo fallida en primer despliegue ({exc}).",
            step="smoke",
            active_digest=new_digest,
            rolled_back=False,
        ) from exc

    redactor.log(
        f"[deploy] completado revision={migration_revision or 'none'} "
        f"smoke_ready_ms={smoke_result.ready_elapsed_ms}"
    )
    return DeployResult(
        previous_digest=d_prev,
        deployed_digest=new_digest,
        migration_revision=migration_revision,
        bootstrap_result=bootstrap_result,
        smoke_result=smoke_result,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquesta el despliegue en dos fases de monitorglucosa."
    )
    parser.add_argument(
        "--digest",
        default=os.environ.get("IMAGE_DIGEST", ""),
        help="Digest sha256:... de la nueva imagen en ECR (o env IMAGE_DIGEST).",
    )
    parser.add_argument(
        "--terraform-dir",
        type=Path,
        default=Path(os.environ.get("TERRAFORM_DIR", str(DEFAULT_TERRAFORM_DIR))),
        help="Directorio raíz de Terraform.",
    )
    parser.add_argument(
        "--ecr-repository",
        default=os.environ.get("ECR_REPOSITORY", DEFAULT_ECR_REPOSITORY),
        help=f"Nombre del repositorio ECR (por defecto: {DEFAULT_ECR_REPOSITORY}).",
    )
    parser.add_argument(
        "--migrator-function",
        default=os.environ.get("MIGRATOR_FUNCTION", DEFAULT_MIGRATOR_FUNCTION),
        help=(
            f"Nombre de la Lambda migrator (por defecto: {DEFAULT_MIGRATOR_FUNCTION})."
        ),
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada CLI."""
    args = _parse_args(argv)
    config = DeployConfig(
        new_digest=args.digest,
        terraform_dir=args.terraform_dir,
        ecr_repository=args.ecr_repository,
        migrator_function_name=args.migrator_function,
        database_name=args.database,
        region=args.region,
    )
    try:
        run_deploy(config)
    except DeployError as exc:
        rollback_flag = "si" if exc.rolled_back else "no"
        print(
            f"[deploy] ERROR paso={exc.step} rollback={rollback_flag}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
