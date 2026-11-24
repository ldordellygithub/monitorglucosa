"""Pruebas basadas en propiedades para `scripts/deploy.py` (Property 6).

Property 6 (design.md · Correctness Properties):
*For any* secuencia de resultados de los pasos del despliegue (comprobación en ECR,
apply, bootstrap, espera, migración y humo, cada uno correcto o fallido), al terminar
`deploy.py` la API sirve `D_prev` o `D_new`. Sirve `D_new` solo si la migración de
`D_new` terminó con `status = ok`, y un fallo de la prueba de humo deja `D_prev` en
servicio cuando existe.

Valida los requisitos 7.4 y 7.5.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from db_bootstrap import BootstrapConfig, BootstrapError, BootstrapResult
from deploy import DeployConfig, DeployError, DeployResult, run_deploy
from runner import CommandResult, Runner
from smoke_test import SmokeTestConfig, SmokeTestError, SmokeTestResult

MigrationOutcome = Literal[
    "ok",
    "status_error",
    "function_error",
    "invoke_nonzero",
    "invalid_json",
    "empty_meta",
]

HEX_LOWER = "0123456789abcdef"
DIGEST_STRATEGY = st.text(alphabet=HEX_LOWER, min_size=64, max_size=64).map(
    lambda h: f"sha256:{h}"
)
DISTINCT_DIGEST_PAIR_STRATEGY = st.lists(
    DIGEST_STRATEGY,
    min_size=2,
    max_size=2,
    unique=True,
).map(lambda pair: (pair[0], pair[1]))
ACCOUNT_ID_STRATEGY = st.text(alphabet="0123456789", min_size=12, max_size=12)
MIGRATION_OUTCOME_STRATEGY: st.SearchStrategy[MigrationOutcome] = st.sampled_from(
    (
        "ok",
        "status_error",
        "function_error",
        "invoke_nonzero",
        "invalid_json",
        "empty_meta",
    )
)


@dataclass(frozen=True)
class StepOutcomes:
    """Resultados generados por Hypothesis para cada paso del despliegue."""

    ecr_ok: bool
    phase1_apply_ok: bool
    outputs_ok: bool
    bootstrap_ok: bool
    wait_ok: bool
    migration: MigrationOutcome
    phase2_apply_ok: bool
    smoke_ok: bool
    rollback_apply_ok: bool


# Combina vectores booleanos totalmente arbitrarios con rutas profundas para garantizar
# alta cobertura sobre migración, Fase 2, prueba de humo y rollback en cada corrida.
_UNIFORM_OUTCOMES_STRATEGY = st.builds(
    StepOutcomes,
    ecr_ok=st.booleans(),
    phase1_apply_ok=st.booleans(),
    outputs_ok=st.booleans(),
    bootstrap_ok=st.booleans(),
    wait_ok=st.booleans(),
    migration=MIGRATION_OUTCOME_STRATEGY,
    phase2_apply_ok=st.booleans(),
    smoke_ok=st.booleans(),
    rollback_apply_ok=st.booleans(),
)
_DEEP_OUTCOMES_STRATEGY = st.builds(
    StepOutcomes,
    ecr_ok=st.just(True),
    phase1_apply_ok=st.just(True),
    outputs_ok=st.just(True),
    bootstrap_ok=st.just(True),
    wait_ok=st.just(True),
    migration=st.one_of(st.just("ok"), MIGRATION_OUTCOME_STRATEGY),
    phase2_apply_ok=st.booleans(),
    smoke_ok=st.booleans(),
    rollback_apply_ok=st.booleans(),
)
STEP_OUTCOMES_STRATEGY = st.one_of(_UNIFORM_OUTCOMES_STRATEGY, _DEEP_OUTCOMES_STRATEGY)


class PropertyDeployWorld:
    """Doble de estado completo para verificar invariantes de `deploy.py`."""

    def __init__(
        self,
        *,
        account_id: str,
        initial_api_digest: str | None,
        outcomes: StepOutcomes,
    ) -> None:
        self.account_id = account_id
        self.cluster_arn = f"arn:aws:rds:us-east-1:{account_id}:cluster:monitorglucosa"
        self.secret_arn = (
            f"arn:aws:secretsmanager:us-east-1:{account_id}:secret:rds!cluster-prop6"
        )
        self.api_host = "prop6api123.execute-api.us-east-1.amazonaws.com"
        self.api_endpoint = f"https://{self.api_host}"

        self.active_api_digest: str | None = initial_api_digest
        self.active_migrator_digest: str | None = initial_api_digest
        self.outcomes = outcomes

        self.apply_calls: list[tuple[str, str]] = []
        self.ecr_checked = False
        self.bootstrap_ran = False
        self.migrator_invoked_digest: str | None = None
        self.migration_succeeded_for_digest: str | None = None
        self.smoke_ran = False
        self.rollback_attempted = False

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        del cwd, env, timeout_s
        cmd = list(command)

        if cmd[:3] == ["aws", "sts", "get-caller-identity"]:
            return CommandResult(returncode=0, stdout=f"{self.account_id}\n")

        if cmd[:3] == ["terraform", "output", "-raw"] and cmd[-1] == "api_image_digest":
            if self.active_api_digest is None:
                return CommandResult(
                    returncode=1,
                    stderr='Error: Output "api_image_digest" not found',
                )
            return CommandResult(returncode=0, stdout=self.active_api_digest)

        if cmd[:3] == ["aws", "ecr", "describe-images"]:
            self.ecr_checked = True
            if not self.outcomes.ecr_ok:
                return CommandResult(returncode=254, stderr="ImageNotFoundException")
            return CommandResult(returncode=0, stdout='{"imageDetails": [{}]}')

        if cmd[:2] == ["terraform", "apply"]:
            api_var = next(
                arg.removeprefix("-var=api_image_digest=")
                for arg in cmd
                if arg.startswith("-var=api_image_digest=")
            )
            mig_var = next(
                arg.removeprefix("-var=migrator_image_digest=")
                for arg in cmd
                if arg.startswith("-var=migrator_image_digest=")
            )
            self.apply_calls.append((api_var, mig_var))
            call_num = len(self.apply_calls)
            if call_num == 1:
                ok = self.outcomes.phase1_apply_ok
            elif call_num == 2 and not self.smoke_ran:
                ok = self.outcomes.phase2_apply_ok
            else:
                self.rollback_attempted = True
                ok = self.outcomes.rollback_apply_ok

            stdout = (
                f"debug account={self.account_id} secret={self.secret_arn}\n"
                "Plan: 0 to add, 1 to change, 0 to destroy.\n"
                "Apply complete! Resources: 0 added, 1 changed, 0 destroyed.\n"
            )
            if not ok:
                return CommandResult(returncode=1, stdout=stdout, stderr="apply failed")
            self.active_api_digest = api_var
            self.active_migrator_digest = mig_var
            return CommandResult(returncode=0, stdout=stdout)

        if cmd[:3] == ["terraform", "output", "-json"]:
            if not self.outcomes.outputs_ok:
                return CommandResult(returncode=1, stderr="output error")
            payload = {
                "cluster_arn": {"value": self.cluster_arn},
                "master_secret_arn": {"value": self.secret_arn, "sensitive": True},
                "api_endpoint": {"value": self.api_endpoint},
            }
            return CommandResult(returncode=0, stdout=json.dumps(payload))

        if cmd[:4] == ["aws", "lambda", "wait", "function-active-v2"]:
            return CommandResult(returncode=0 if self.outcomes.wait_ok else 255)

        if cmd[:3] == ["aws", "lambda", "invoke"]:
            self.migrator_invoked_digest = self.active_migrator_digest
            outcome = self.outcomes.migration
            if outcome == "invoke_nonzero":
                return CommandResult(returncode=255, stderr="invoke error")
            if outcome == "empty_meta":
                Path(cmd[-1]).write_text('{"status": "ok"}', encoding="utf-8")
                return CommandResult(returncode=0, stdout="")
            if outcome == "function_error":
                Path(cmd[-1]).write_text('{"status": "ok"}', encoding="utf-8")
                return CommandResult(
                    returncode=0,
                    stdout=json.dumps(
                        {"StatusCode": 200, "FunctionError": "Unhandled"}
                    ),
                )
            if outcome == "invalid_json":
                Path(cmd[-1]).write_text("{not-json", encoding="utf-8")
                return CommandResult(
                    returncode=0,
                    stdout=json.dumps({"StatusCode": 200}),
                )
            if outcome == "status_error":
                Path(cmd[-1]).write_text(
                    json.dumps({"status": "error", "revision": None}),
                    encoding="utf-8",
                )
                return CommandResult(
                    returncode=0,
                    stdout=json.dumps({"StatusCode": 200}),
                )

            Path(cmd[-1]).write_text(
                json.dumps({"status": "ok", "revision": "20261123_baseline"}),
                encoding="utf-8",
            )
            self.migration_succeeded_for_digest = self.active_migrator_digest
            return CommandResult(
                returncode=0,
                stdout=json.dumps({"StatusCode": 200}),
            )

        raise AssertionError(f"Comando inesperado en doble de Property 6: {cmd}")

    def bootstrap(self, cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        self.bootstrap_ran = True
        if not self.outcomes.bootstrap_ok:
            raise BootstrapError("DatabaseErrorException")
        return BootstrapResult(attempts=1, elapsed_ms=15)

    def smoke(self, cfg: SmokeTestConfig) -> SmokeTestResult:
        del cfg
        self.smoke_ran = True
        if not self.outcomes.smoke_ok:
            raise SmokeTestError("smoke failed")
        return SmokeTestResult(
            ready_status=200,
            ready_attempts=1,
            ready_elapsed_ms=150,
            unauth_status=401,
            unauth_elapsed_ms=20,
        )


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5")
@settings(max_examples=200, deadline=None)
@given(
    digests=DISTINCT_DIGEST_PAIR_STRATEGY,
    account_id=ACCOUNT_ID_STRATEGY,
    outcomes=STEP_OUTCOMES_STRATEGY,
)
def test_property_6_nunca_se_sirve_d_new_sin_migraciones_y_humo_revierte_a_d_prev(
    digests: tuple[str, str],
    account_id: str,
    outcomes: StepOutcomes,
) -> None:
    """Property 6 sobre un despliegue existente (`D_prev` en servicio)."""
    d_prev, d_new = digests

    world = PropertyDeployWorld(
        account_id=account_id,
        initial_api_digest=d_prev,
        outcomes=outcomes,
    )
    logs: list[str] = []

    deploy_result: DeployResult | None = None
    deploy_error: DeployError | None = None
    try:
        deploy_result = run_deploy(
            DeployConfig(new_digest=d_new),
            runner=world,
            bootstrap_fn=world.bootstrap,
            smoke_fn=world.smoke,
            log=logs.append,
        )
    except DeployError as exc:
        deploy_error = exc

    if deploy_result is not None:
        event("resultado=exito_d_new")
    elif deploy_error is not None:
        event(f"fallo={deploy_error.step}:rollback={deploy_error.rolled_back}")

    # Invariante 1: al terminar, la API siempre sirve D_prev o D_new.
    assert world.active_api_digest in {d_prev, d_new}

    # Invariante 2: nunca se sirve D_new si la migración de D_new no terminó en "ok".
    if world.active_api_digest == d_new:
        assert world.migration_succeeded_for_digest == d_new
        assert outcomes.migration == "ok"
        assert outcomes.ecr_ok
        assert outcomes.phase1_apply_ok
        assert outcomes.outputs_ok
        assert outcomes.bootstrap_ok
        assert outcomes.wait_ok
        assert outcomes.phase2_apply_ok

    # Invariante 3: si la prueba de humo falló (y el rollback se aplica), queda D_prev.
    if world.smoke_ran and not outcomes.smoke_ok:
        assert deploy_error is not None
        assert deploy_result is None
        assert world.rollback_attempted
        if outcomes.rollback_apply_ok:
            assert world.active_api_digest == d_prev
            assert deploy_error.rolled_back is True
            assert deploy_error.active_digest == d_prev
        else:
            assert deploy_error.rolled_back is False

    # Invariante 4: el despliegue solo retorna éxito si TODOS los pasos pasan.
    all_steps_ok = (
        outcomes.ecr_ok
        and outcomes.phase1_apply_ok
        and outcomes.outputs_ok
        and outcomes.bootstrap_ok
        and outcomes.wait_ok
        and outcomes.migration == "ok"
        and outcomes.phase2_apply_ok
        and outcomes.smoke_ok
    )
    if all_steps_ok:
        assert deploy_result is not None
        assert deploy_error is None
        assert deploy_result.deployed_digest == d_new
        assert world.active_api_digest == d_new
    else:
        assert deploy_result is None
        assert deploy_error is not None

    # Invariante 5 (ADR 0008 / NFR-5): ID de cuenta y secreto nunca en logs sin máscara.
    assert f"::add-mask::{account_id}" in logs
    non_mask_logs = [line for line in logs if not line.startswith("::add-mask::")]
    assert all(account_id not in line for line in non_mask_logs)
    assert all(world.secret_arn not in line for line in non_mask_logs)
    assert all(world.api_host not in line for line in non_mask_logs)


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5")
@settings(max_examples=100, deadline=None)
@given(
    d_new=DIGEST_STRATEGY,
    account_id=ACCOUNT_ID_STRATEGY,
    outcomes=STEP_OUTCOMES_STRATEGY,
)
def test_property_6_primer_despliegue_sin_d_prev_solo_triunfa_con_migracion_y_humo_ok(
    d_new: str,
    account_id: str,
    outcomes: StepOutcomes,
) -> None:
    """Property 6 en primer despliegue (`D_prev` ausente): sin ECR ni rollback."""
    world = PropertyDeployWorld(
        account_id=account_id,
        initial_api_digest=None,
        outcomes=outcomes,
    )
    logs: list[str] = []

    deploy_result: DeployResult | None = None
    deploy_error: DeployError | None = None
    try:
        deploy_result = run_deploy(
            DeployConfig(new_digest=d_new),
            runner=world,
            bootstrap_fn=world.bootstrap,
            smoke_fn=world.smoke,
            log=logs.append,
        )
    except DeployError as exc:
        deploy_error = exc

    assert not world.ecr_checked
    assert not world.rollback_attempted
    assert len(world.apply_calls) <= 1
    assert world.active_api_digest in {None, d_new}

    first_deploy_ok = (
        outcomes.phase1_apply_ok
        and outcomes.outputs_ok
        and outcomes.bootstrap_ok
        and outcomes.wait_ok
        and outcomes.migration == "ok"
        and outcomes.smoke_ok
    )
    if first_deploy_ok:
        assert deploy_result is not None
        assert deploy_error is None
        assert deploy_result.previous_digest is None
        assert deploy_result.deployed_digest == d_new
        assert world.migration_succeeded_for_digest == d_new
        assert world.active_api_digest == d_new
    else:
        assert deploy_result is None
        assert deploy_error is not None
        assert deploy_error.rolled_back is False

    non_mask_logs = [line for line in logs if not line.startswith("::add-mask::")]
    assert all(account_id not in line for line in non_mask_logs)
    assert all(world.secret_arn not in line for line in non_mask_logs)


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5")
@settings(max_examples=50, deadline=None)
@given(
    digest=DIGEST_STRATEGY,
    account_id=ACCOUNT_ID_STRATEGY,
    outcomes=STEP_OUTCOMES_STRATEGY,
)
def test_property_6_redespliegue_mismo_digest_mantiene_invariantes(
    digest: str,
    account_id: str,
    outcomes: StepOutcomes,
) -> None:
    """Property 6 cuando `D_prev == D_new` (cambio de infra o `workflow_dispatch`)."""
    world = PropertyDeployWorld(
        account_id=account_id,
        initial_api_digest=digest,
        outcomes=outcomes,
    )
    logs: list[str] = []

    deploy_result: DeployResult | None = None
    deploy_error: DeployError | None = None
    try:
        deploy_result = run_deploy(
            DeployConfig(new_digest=digest),
            runner=world,
            bootstrap_fn=world.bootstrap,
            smoke_fn=world.smoke,
            log=logs.append,
        )
    except DeployError as exc:
        deploy_error = exc

    assert world.active_api_digest == digest
    same_digest_ok = (
        outcomes.ecr_ok
        and outcomes.phase1_apply_ok
        and outcomes.outputs_ok
        and outcomes.bootstrap_ok
        and outcomes.wait_ok
        and outcomes.migration == "ok"
        and outcomes.smoke_ok
    )
    if same_digest_ok:
        assert deploy_result is not None
        assert deploy_error is None
        assert world.migration_succeeded_for_digest == digest
    else:
        assert deploy_result is None
        assert deploy_error is not None
