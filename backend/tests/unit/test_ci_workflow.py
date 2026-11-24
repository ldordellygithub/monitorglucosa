"""Pruebas del workflow de integración continua y del ruleset de `main`.

Verifica los requisitos 7.1, NFR-1, NFR-4 y NFR-5 sobre `.github/workflows/ci.yml`,
`.github/rulesets/main.json` y `backend/pyproject.toml`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RULESET_PATH = REPO_ROOT / ".github" / "rulesets" / "main.json"
BACKEND_PYPROJECT_PATH = REPO_ROOT / "backend" / "pyproject.toml"
SHA40_USES_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
DOCKER_DIGEST_PATTERN = re.compile(r"@sha256:[0-9a-f]{64}")


def _load_ci_workflow() -> dict[str, Any]:
    raw = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _all_run_scripts(workflow: dict[str, Any]) -> str:
    chunks: list[str] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                chunks.append(str(step["run"]))
    return "\n".join(chunks)


@pytest.mark.req("fase-1a:7.1")
def test_ci_workflow_has_expected_jobs_and_ruleset_requires_ci() -> None:
    """ci.yml define changes/backend/compose/infra/ci y el ruleset exige `ci`."""
    wf = _load_ci_workflow()
    jobs = wf["jobs"]

    assert {"changes", "backend", "compose", "infra", "ci"}.issubset(jobs.keys())
    assert wf["permissions"] == {"contents": "read"}
    for job_name, job in jobs.items():
        assert "permissions" not in job, (
            f"El job {job_name} no debe sobrescribir permisos de solo lectura"
        )

    ci_job = jobs["ci"]
    assert ci_job["if"] == "always()"
    assert set(ci_job["needs"]) == {"changes", "backend", "compose", "infra"}

    # El filtro de rutas usa git diff -z propio (anti-evasión con rutas no ASCII).
    changes_steps = jobs["changes"]["steps"]
    assert all(
        "paths-filter" not in str(step.get("uses", "")) for step in changes_steps
    )
    changes_runs = "\n".join(str(step.get("run", "")) for step in changes_steps)
    assert '"git", "diff", "--name-only", "-z"' in changes_runs
    assert 'split("\\0")' in changes_runs
    assert ".github/rulesets/main\\.json" in changes_runs

    # El ruleset de main preserva los 4 checks previos, añade `ci`, modo estricto y
    # cero bypass_actors.
    ruleset = json.loads(RULESET_PATH.read_text(encoding="utf-8"))
    assert ruleset["enforcement"] == "active"
    assert ruleset["bypass_actors"] == []
    status_rules = [
        rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
    ]
    assert len(status_rules) == 1
    params = status_rules[0]["parameters"]
    assert params["strict_required_status_checks_policy"] is True
    contexts = {entry["context"] for entry in params["required_status_checks"]}
    assert {
        "spec-lint",
        "architecture",
        "traceability",
        "pr-title",
        "ci",
    }.issubset(contexts)


@pytest.mark.req("fase-1a:7.1", "fase-1a:NFR-1")
def test_ci_backend_enforces_quality_openapi_coverage_and_security() -> None:
    """backend exige ruff, mypy, import-linter, pytest --cov>=80, OpenAPI y semgrep."""
    wf = _load_ci_workflow()
    backend_job = wf["jobs"]["backend"]
    backend_runs = "\n".join(
        str(step.get("run", "")) for step in backend_job.get("steps", [])
    )

    assert "postgres" in backend_job.get("services", {})
    assert DOCKER_DIGEST_PATTERN.search(backend_job["services"]["postgres"]["image"])

    for expected in (
        "uv --directory backend sync --locked",
        "ruff check .",
        "ruff format --check .",
        "mypy",
        "lint-imports",
        "GRANT mg_api TO mg_admin WITH ADMIN OPTION",
        'pytest -m "not e2e" --cov --cov-fail-under=80',
        "tools/export_openapi.py --check",
        "openapi-spec-validator",
        "--config p/owasp-top-ten",
        "backend/tools",
    ):
        assert expected in backend_runs, f"Falta `{expected}` en el job backend"

    assert re.search(
        r"semgrep/semgrep:1\.184\.0@sha256:[0-9a-f]{64}",
        backend_runs,
    )

    # Verifica también la configuración de cobertura en backend/pyproject.toml (NFR-1).
    pyproject_text = BACKEND_PYPROJECT_PATH.read_text(encoding="utf-8")
    assert 'source = ["src/domain", "src/application"]' in pyproject_text
    assert "fail_under = 80" in pyproject_text


@pytest.mark.req("fase-1a:7.1", "fase-1a:NFR-4", "fase-1a:NFR-5")
def test_ci_enforces_sha_pinning_checkov_gitleaks_and_no_script_injection() -> None:
    """Todas las acciones van por SHA; infra ejecuta Checkov; gitleaks y dep-review."""
    wf = _load_ci_workflow()

    uses_entries: list[str] = []
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            if "uses" not in step:
                continue
            uses = str(step["uses"])
            uses_entries.append(uses)
            assert SHA40_USES_PATTERN.match(uses), f"Acción sin SHA de 40 hex: {uses}"
            if uses.startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False
            if uses.startswith("astral-sh/setup-uv@"):
                uv_version = str(step.get("with", {}).get("version", ""))
                assert re.match(r"^\d+\.\d+\.\d+$", uv_version), (
                    f"setup-uv debe fijar versión exacta, recibido: {uv_version!r}"
                )

    assert len(uses_entries) >= 6
    assert any("dependency-review-action@" in u for u in uses_entries)

    # Infra ejecuta terraform fmt/validate/test y Checkov fijado por digest (NFR-4).
    infra_runs = "\n".join(
        str(step.get("run", "")) for step in wf["jobs"]["infra"]["steps"]
    )
    for expected in (
        "terraform -chdir=infra/terraform fmt -check -recursive",
        "terraform -chdir=infra/terraform init -backend=false",
        "terraform -chdir=infra/terraform validate",
        "terraform -chdir=infra/terraform test",
    ):
        assert expected in infra_runs
    assert re.search(
        r"bridgecrew/checkov:3\.2\.517@sha256:[0-9a-f]{64}",
        infra_runs,
    )

    # Compose construye para linux/amd64 sin provenance ni sbom y corre e2e.
    compose_runs = "\n".join(
        str(step.get("run", "")) for step in wf["jobs"]["compose"]["steps"]
    )
    assert "--platform linux/amd64" in compose_runs
    assert "--provenance=false" in compose_runs
    assert "--sbom=false" in compose_runs
    assert "docker compose up -d --build --wait" in compose_runs
    assert "pytest -m e2e" in compose_runs

    # gitleaks presente con verificación SHA-256 (NFR-5).
    all_runs = _all_run_scripts(wf)
    assert "gitleaks" in all_runs
    assert "sha256sum -c -" in all_runs

    # Ningún bloque `run:` interpola directamente expresiones `${{ ... }}`.
    assert "${{" not in all_runs, (
        "No interpole expresiones GitHub ${{ }} dentro de bloques run:; use env:"
    )
