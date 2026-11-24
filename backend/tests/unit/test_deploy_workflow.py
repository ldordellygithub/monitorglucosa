"""Pruebas del workflow de despliegue continuo a producción (`deploy.yml`).

Verifica los requisitos 7.2, 7.3, 7.4, 7.5 y NFR-5 sobre `.github/workflows/deploy.yml`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
SHA40_USES_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def _load_deploy_workflow() -> dict[object, Any]:
    raw = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _job_runs(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


@pytest.mark.req("fase-1a:7.2", "fase-1a:7.3")
def test_deploy_workflow_separates_build_and_prod_oidc_environment() -> None:
    """build corre sin AWS; deploy exige main, prod, OIDC y concurrency."""
    wf = _load_deploy_workflow()

    # PyYAML interpreta `on:` como clave booleana True en YAML 1.1.
    triggers = wf.get("on", wf.get(True))
    assert isinstance(triggers, dict)
    assert triggers["push"]["branches"] == ["main"]
    assert set(triggers["push"]["paths"]) == {
        "backend/**",
        "infra/**",
        "scripts/**",
        "compose.yaml",
        ".github/workflows/deploy.yml",
    }
    assert "workflow_dispatch" in triggers

    assert wf["permissions"] == {"contents": "read"}

    jobs = wf["jobs"]
    assert set(jobs.keys()) == {"build", "deploy"}

    # `build` corre solo en main y sin acceso a AWS ni secretos de prod.
    build_job = jobs["build"]
    assert build_job["if"] == "github.ref == 'refs/heads/main'"
    assert "permissions" not in build_job
    assert "environment" not in build_job
    build_serialized = yaml.safe_dump(build_job)
    assert "configure-aws-credentials" not in build_serialized
    assert "AWS_DEPLOY_ROLE_ARN" not in build_serialized
    assert "TF_STATE_BUCKET" not in build_serialized

    # `deploy` exige main, aprobación del entorno prod, concurrencia serializada y OIDC.
    deploy_job = jobs["deploy"]
    assert deploy_job["needs"] == "build"
    assert deploy_job["if"] == "github.ref == 'refs/heads/main'"
    assert deploy_job["environment"] == "prod"
    assert deploy_job["timeout-minutes"] == 30
    assert deploy_job["concurrency"] == {
        "group": "deploy-prod",
        "cancel-in-progress": False,
    }
    assert deploy_job["permissions"] == {"contents": "read", "id-token": "write"}

    # Herramientas y dependencias se instalan ANTES de asumir OIDC y sin caché.
    deploy_steps = deploy_job["steps"]
    idx_tf = next(
        i
        for i, s in enumerate(deploy_steps)
        if str(s.get("uses", "")).startswith("hashicorp/setup-terraform@")
    )
    idx_uv = next(
        i
        for i, s in enumerate(deploy_steps)
        if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")
    )
    idx_sync = next(
        i
        for i, s in enumerate(deploy_steps)
        if "uv --directory scripts sync --locked --no-dev" in str(s.get("run", ""))
    )
    idx_aws = next(
        i
        for i, s in enumerate(deploy_steps)
        if str(s.get("uses", "")).startswith("aws-actions/configure-aws-credentials@")
    )
    assert idx_tf < idx_aws
    assert idx_uv < idx_aws
    assert idx_sync < idx_aws
    assert deploy_steps[idx_uv]["with"]["enable-cache"] is False

    aws_with = deploy_steps[idx_aws]["with"]
    assert aws_with["role-to-assume"] == "${{ secrets.AWS_DEPLOY_ROLE_ARN }}"
    assert aws_with["aws-region"] == "us-east-1"
    assert aws_with["mask-aws-account-id"] is True
    assert "aws-access-key-id" not in aws_with
    assert "aws-secret-access-key" not in aws_with


@pytest.mark.req("fase-1a:7.3", "fase-1a:7.4", "fase-1a:7.5", "fase-1a:NFR-5")
def test_deploy_workflow_enforces_sha_pinning_integrity_ecr_digest_and_deploy_py() -> (
    None
):
    """Acciones por SHA, artefacto verificado por SHA-256, ECR inmutable y deploy.py."""
    wf = _load_deploy_workflow()
    jobs = wf["jobs"]

    for job in jobs.values():
        for step in job.get("steps", []):
            if "uses" not in step:
                continue
            uses = str(step["uses"])
            assert SHA40_USES_PATTERN.match(uses), f"Acción sin SHA de 40 hex: {uses}"
            if uses.startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False
            if uses.startswith("astral-sh/setup-uv@"):
                assert step.get("with", {}).get("version") == "0.13.5"
            if uses.startswith("hashicorp/setup-terraform@"):
                assert step.get("with", {}).get("terraform_version") == "1.16.6"
                assert step.get("with", {}).get("terraform_wrapper") is False
            if uses.startswith("actions/upload-artifact@"):
                assert step.get("with", {}).get("retention-days") == 3
                assert step.get("with", {}).get("if-no-files-found") == "error"

    # `build`: imagen linux/amd64 sin provenance/sbom, probada sin rebuild y guardada.
    build_runs = _job_runs(jobs["build"])
    for expected in (
        "--platform linux/amd64",
        "--provenance=false",
        "--sbom=false",
        "compose-image.yml",
        "up -d --no-build --wait",
        "pytest -m e2e",
        "docker save",
        "sha256sum",
    ):
        assert expected in build_runs

    # `deploy`: verificación SHA-256, limpieza, backend S3 silencioso, ECR y deploy.py.
    deploy_runs = _job_runs(jobs["deploy"])
    for expected in (
        "sha256sum -c -",
        "docker load",
        'rm -f "${ARCHIVE}"',
        '-backend-config="bucket=${TF_STATE_BUCKET}" >/dev/null 2>&1',
        "^[0-9]{12}$",
        "::add-mask::",
        "docker logout",
        "docker push --quiet",
        "aws ecr describe-images",
        "^sha256:[0-9a-f]{64}$",
        "uv --directory scripts sync --locked --no-dev",
        "uv --directory scripts run --no-sync python deploy.py",
        '--digest "${IMAGE_DIGEST}"',
        '--region "${AWS_REGION}"',
    ):
        assert expected in deploy_runs

    # Cero artefactos de planes Terraform y cero `${{ }}` dentro de bloques `run:`.
    all_runs = f"{build_runs}\n{deploy_runs}"
    assert "${{" not in all_runs
    assert ".tfplan" not in yaml.safe_dump(wf)
