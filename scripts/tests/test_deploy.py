"""Pruebas unitarias de `scripts/deploy.py` y `scripts/runner.py` (7.4, 7.5, NFR-5)."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from db_bootstrap import BootstrapConfig, BootstrapError, BootstrapResult
from deploy import DeployConfig, DeployError, main, run_deploy
from runner import CommandResult, Runner, SubprocessRunner
from smoke_test import SmokeTestConfig, SmokeTestError, SmokeTestResult

ACCOUNT_ID = "123456789012"
D_PREV = "sha256:" + "a" * 64
D_NEW = "sha256:" + "b" * 64
CLUSTER_ARN = f"arn:aws:rds:us-east-1:{ACCOUNT_ID}:cluster:monitorglucosa"
SECRET_ARN = f"arn:aws:secretsmanager:us-east-1:{ACCOUNT_ID}:secret:rds!cluster-xyz"
API_HOST = "xyz9876543.execute-api.us-east-1.amazonaws.com"
API_ENDPOINT = f"https://{API_HOST}"


class FakeDeployWorld:
    """Simula STS, ECR, Terraform y Lambda para verificar el orden y estado final."""

    def __init__(
        self,
        *,
        initial_api_digest: str | None = D_PREV,
        sts_stdout: str | None = None,
        read_prev_error: str | None = None,
        ecr_has_prev: bool = True,
        phase1_ok: bool = True,
        phase2_ok: bool = True,
        rollback_ok: bool = True,
        wait_ok: bool = True,
        invoke_exit_code: int = 0,
        invoke_stdout_override: str | None = None,
        invoke_meta: dict[str, object] | None = None,
        migrator_payload: dict[str, object] | None = None,
    ) -> None:
        self.active_api_digest: str | None = initial_api_digest
        self.active_migrator_digest: str | None = initial_api_digest
        self.sts_stdout = f"{ACCOUNT_ID}\n" if sts_stdout is None else sts_stdout
        self.read_prev_error = read_prev_error
        self.ecr_has_prev = ecr_has_prev
        self.phase1_ok = phase1_ok
        self.phase2_ok = phase2_ok
        self.rollback_ok = rollback_ok
        self.wait_ok = wait_ok
        self.invoke_exit_code = invoke_exit_code
        self.invoke_stdout_override = invoke_stdout_override
        self.invoke_meta = (
            invoke_meta if invoke_meta is not None else {"StatusCode": 200}
        )
        self.migrator_payload = (
            migrator_payload
            if migrator_payload is not None
            else {"status": "ok", "revision": "20261123_baseline"}
        )
        self.events: list[str] = []
        self.apply_calls: list[tuple[str, str]] = []

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
            self.events.append("sts")
            return CommandResult(returncode=0, stdout=self.sts_stdout)

        if cmd[:3] == ["terraform", "output", "-raw"] and cmd[-1] == "api_image_digest":
            self.events.append("tf_read_prev")
            if self.read_prev_error is not None:
                return CommandResult(returncode=1, stderr=self.read_prev_error)
            if self.active_api_digest is None:
                return CommandResult(
                    returncode=1,
                    stderr='Error: Output "api_image_digest" not found',
                )
            return CommandResult(returncode=0, stdout=self.active_api_digest)

        if cmd[:3] == ["aws", "ecr", "describe-images"]:
            self.events.append("ecr_check")
            if not self.ecr_has_prev:
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
                self.events.append("tf_apply_phase1")
                ok = self.phase1_ok
            elif call_num == 2:
                self.events.append("tf_apply_phase2")
                ok = self.phase2_ok
            else:
                self.events.append("tf_apply_rollback")
                ok = self.rollback_ok

            verbose_stdout = (
                "aws_lambda_function.api: modifying "
                f"arn:aws:lambda:us-east-1:{ACCOUNT_ID}:fn\n"
                "  Plan: descripcion de atributo que NO debe filtrarse\n"
                "Plan: 0 to add, 1 to change, 0 to destroy.\n"
                "Apply complete! Resources: 0 added, 1 changed, 0 destroyed.\n"
            )
            if not ok:
                return CommandResult(returncode=1, stdout=verbose_stdout, stderr="err")
            self.active_api_digest = api_var
            self.active_migrator_digest = mig_var
            return CommandResult(returncode=0, stdout=verbose_stdout)

        if cmd[:3] == ["terraform", "output", "-json"]:
            self.events.append("tf_outputs")
            payload = {
                "cluster_arn": {"value": CLUSTER_ARN},
                "master_secret_arn": {"value": SECRET_ARN, "sensitive": True},
                "api_endpoint": {"value": API_ENDPOINT},
            }
            return CommandResult(returncode=0, stdout=json.dumps(payload))

        if cmd[:4] == ["aws", "lambda", "wait", "function-active-v2"]:
            self.events.append("migrator_wait")
            return CommandResult(returncode=0 if self.wait_ok else 255)

        if cmd[:3] == ["aws", "lambda", "invoke"]:
            self.events.append("migrator_invoke")
            assert "--cli-read-timeout=310" in cmd
            assert "--output=json" in cmd
            if self.invoke_exit_code != 0:
                return CommandResult(returncode=self.invoke_exit_code, stderr="fail")
            Path(cmd[-1]).write_text(
                json.dumps(self.migrator_payload),
                encoding="utf-8",
            )
            stdout_text = (
                self.invoke_stdout_override
                if self.invoke_stdout_override is not None
                else json.dumps(self.invoke_meta)
            )
            return CommandResult(returncode=0, stdout=stdout_text)

        raise AssertionError(f"Comando no esperado: {cmd}")


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5", "fase-1a:NFR-5")
def test_deploy_en_dos_fases_exitoso_enmascara_cuenta_y_resume_plan() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV)
    logs: list[str] = []

    def fake_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        assert cfg.cluster_arn == CLUSTER_ARN
        assert cfg.secret_arn == SECRET_ARN
        assert runner is world
        world.events.append("bootstrap")
        return BootstrapResult(attempts=1, elapsed_ms=30)

    def fake_smoke(cfg: SmokeTestConfig) -> SmokeTestResult:
        assert cfg.api_endpoint == API_ENDPOINT
        assert cfg.max_wait_s == 120.0
        assert cfg.request_timeout_s == 40.0
        world.events.append("smoke")
        return SmokeTestResult(
            ready_status=200,
            ready_attempts=1,
            ready_elapsed_ms=250,
            unauth_status=401,
            unauth_elapsed_ms=40,
        )

    result = run_deploy(
        DeployConfig(new_digest=D_NEW),
        runner=world,
        bootstrap_fn=fake_bootstrap,
        smoke_fn=fake_smoke,
        log=logs.append,
    )

    assert result.previous_digest == D_PREV
    assert result.deployed_digest == D_NEW
    assert result.migration_revision == "20261123_baseline"
    assert world.active_api_digest == D_NEW
    assert world.active_migrator_digest == D_NEW
    assert world.events == [
        "sts",
        "tf_read_prev",
        "ecr_check",
        "tf_apply_phase1",
        "tf_outputs",
        "bootstrap",
        "migrator_wait",
        "migrator_invoke",
        "tf_apply_phase2",
        "smoke",
    ]
    assert world.apply_calls == [(D_PREV, D_NEW), (D_NEW, D_NEW)]

    # Enmascaramiento obligatorio (ADR 0008 / NFR-5).
    assert f"::add-mask::{ACCOUNT_ID}" in logs
    assert f"::add-mask::{SECRET_ARN}" in logs
    assert f"::add-mask::{API_ENDPOINT}" in logs
    assert f"::add-mask::{API_HOST}" in logs
    non_mask_logs = [line for line in logs if not line.startswith("::add-mask::")]
    assert all(ACCOUNT_ID not in line for line in non_mask_logs)
    assert all(SECRET_ARN not in line for line in non_mask_logs)
    assert all(API_HOST not in line for line in non_mask_logs)
    assert all("aws_lambda_function.api" not in line for line in non_mask_logs)
    assert all("NO debe filtrarse" not in line for line in non_mask_logs)
    assert any("Plan: 0 to add, 1 to change, 0 to destroy." in s for s in non_mask_logs)
    assert any("Apply complete!" in s for s in non_mask_logs)


@pytest.mark.req("fase-1a:7.4")
def test_deploy_falla_cerrado_si_sts_no_devuelve_cuenta_de_12_digitos() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV, sts_stdout="invalid-account\n")

    with pytest.raises(DeployError) as exc_info:
        run_deploy(DeployConfig(new_digest=D_NEW), runner=world, log=lambda _: None)

    assert exc_info.value.step == "sts"
    assert world.events == ["sts"]
    assert world.apply_calls == []


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5")
def test_deploy_no_confunde_error_404_de_backend_con_primer_despliegue() -> None:
    world = FakeDeployWorld(
        initial_api_digest=D_PREV,
        read_prev_error="Error loading state: S3 bucket 404 Not Found",
    )

    with pytest.raises(DeployError) as exc_info:
        run_deploy(DeployConfig(new_digest=D_NEW), runner=world, log=lambda _: None)

    assert exc_info.value.step == "read_d_prev"
    assert world.apply_calls == []


@pytest.mark.req("fase-1a:7.4")
def test_deploy_se_detiene_sin_cambios_si_d_prev_falta_en_ecr() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV, ecr_has_prev=False)

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            log=lambda _: None,
        )

    assert exc_info.value.step == "ecr_check"
    assert exc_info.value.active_digest == D_PREV
    assert world.apply_calls == []
    assert world.active_api_digest == D_PREV


@pytest.mark.req("fase-1a:7.4")
def test_deploy_mantiene_d_prev_si_falla_bootstrap() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV)

    def failing_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        world.events.append("bootstrap")
        raise BootstrapError("DatabaseErrorException")

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            bootstrap_fn=failing_bootstrap,
            log=lambda _: None,
        )

    assert exc_info.value.step == "bootstrap"
    assert exc_info.value.active_digest == D_PREV
    assert world.active_api_digest == D_PREV
    assert "migrator_wait" not in world.events
    assert "tf_apply_phase2" not in world.events


@pytest.mark.req("fase-1a:7.4")
def test_deploy_mantiene_d_prev_si_falla_wait_de_migrator() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV, wait_ok=False)

    def ok_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        world.events.append("bootstrap")
        return BootstrapResult(attempts=1, elapsed_ms=10)

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            bootstrap_fn=ok_bootstrap,
            log=lambda _: None,
        )

    assert exc_info.value.step == "migrator_wait"
    assert exc_info.value.active_digest == D_PREV
    assert world.active_api_digest == D_PREV
    assert "migrator_invoke" not in world.events
    assert "tf_apply_phase2" not in world.events


@pytest.mark.req("fase-1a:7.4")
@pytest.mark.parametrize(
    ("invoke_stdout_override", "invoke_meta", "migrator_payload"),
    [
        (None, {"StatusCode": 200}, {"status": "error", "revision": None}),
        (None, {"StatusCode": 200, "FunctionError": "Unhandled"}, {"status": "ok"}),
        ("", {"StatusCode": 200}, {"status": "ok"}),
        (None, {"StatusCode": "200"}, {"status": "ok"}),
    ],
)
def test_deploy_mantiene_d_prev_si_migracion_falla(
    invoke_stdout_override: str | None,
    invoke_meta: dict[str, object],
    migrator_payload: dict[str, object],
) -> None:
    world = FakeDeployWorld(
        initial_api_digest=D_PREV,
        invoke_stdout_override=invoke_stdout_override,
        invoke_meta=invoke_meta,
        migrator_payload=migrator_payload,
    )

    def ok_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        world.events.append("bootstrap")
        return BootstrapResult(attempts=1, elapsed_ms=10)

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            bootstrap_fn=ok_bootstrap,
            log=lambda _: None,
        )

    assert exc_info.value.step == "migrator_invoke"
    assert exc_info.value.active_digest == D_PREV
    assert world.active_api_digest == D_PREV
    assert "tf_apply_phase2" not in world.events


@pytest.mark.req("fase-1a:7.5")
def test_deploy_hace_rollback_a_d_prev_si_falla_prueba_de_humo() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV)

    def ok_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        world.events.append("bootstrap")
        return BootstrapResult(attempts=1, elapsed_ms=10)

    def failing_smoke(cfg: SmokeTestConfig) -> SmokeTestResult:
        del cfg
        world.events.append("smoke")
        raise SmokeTestError("GET /health/ready timeout tras 120 s")

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            bootstrap_fn=ok_bootstrap,
            smoke_fn=failing_smoke,
            log=lambda _: None,
        )

    assert exc_info.value.step == "smoke"
    assert exc_info.value.rolled_back is True
    assert exc_info.value.active_digest == D_PREV
    assert world.active_api_digest == D_PREV
    assert world.apply_calls == [(D_PREV, D_NEW), (D_NEW, D_NEW), (D_PREV, D_NEW)]


@pytest.mark.req("fase-1a:7.4", "fase-1a:7.5")
def test_primer_despliegue_sin_d_prev_no_consulta_ecr_ni_revierte_si_falla_humo() -> (
    None
):
    world = FakeDeployWorld(initial_api_digest=None)

    def ok_bootstrap(cfg: BootstrapConfig, runner: Runner) -> BootstrapResult:
        del cfg, runner
        world.events.append("bootstrap")
        return BootstrapResult(attempts=1, elapsed_ms=10)

    def failing_smoke(cfg: SmokeTestConfig) -> SmokeTestResult:
        del cfg
        world.events.append("smoke")
        raise SmokeTestError("401 esperado, recibido 500")

    with pytest.raises(DeployError) as exc_info:
        run_deploy(
            DeployConfig(new_digest=D_NEW),
            runner=world,
            bootstrap_fn=ok_bootstrap,
            smoke_fn=failing_smoke,
            log=lambda _: None,
        )

    assert exc_info.value.step == "smoke"
    assert exc_info.value.rolled_back is False
    assert "ecr_check" not in world.events
    assert world.apply_calls == [(D_NEW, D_NEW)]


def test_deploy_rechaza_parametros_invalidos_antes_de_llamar_aws() -> None:
    world = FakeDeployWorld(initial_api_digest=D_PREV)

    invalid_configs = [
        DeployConfig(new_digest="latest"),
        DeployConfig(new_digest=D_NEW, region="--bad"),
        DeployConfig(new_digest=D_NEW, ecr_repository="--inject"),
        DeployConfig(new_digest=D_NEW, migrator_function_name="-bad-fn"),
        DeployConfig(new_digest=D_NEW, database_name="bad;db"),
        DeployConfig(new_digest=D_NEW, migrator_read_timeout_s=0),
    ]
    for cfg in invalid_configs:
        with pytest.raises(DeployError) as exc_info:
            run_deploy(cfg, runner=world)
        assert exc_info.value.step == "validate"

    assert world.events == []


def test_deploy_cli_devuelve_1_con_digest_invalido() -> None:
    assert main(["--digest", "invalido"]) == 1


def test_subprocess_runner_ejecuta_y_controla_timeout() -> None:
    runner = SubprocessRunner()

    ok = runner.run([sys.executable, "-c", "print('hola')"])
    assert ok.returncode == 0
    assert ok.stdout.strip() == "hola"

    timeout_res = runner.run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout_s=0.05,
    )
    assert timeout_res.returncode == 124
    assert "timeout" in timeout_res.stderr

    with pytest.raises(ValueError, match="vacío"):
        runner.run([])
