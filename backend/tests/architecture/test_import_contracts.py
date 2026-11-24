"""Pruebas de arquitectura: los contratos de import-linter de `structure.md`.

Cada caso copia `src/` y `pyproject.toml` a un directorio temporal, añade un módulo
que viola una regla y comprueba que `lint-imports` falla nombrando el contrato roto.
"""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

CONTRACT_NAMES = [
    contract["name"]
    for contract in tomllib.loads((BACKEND / "pyproject.toml").read_text("utf-8"))[
        "tool"
    ]["importlinter"]["contracts"]
]
(
    LAYERS,
    API_NOT_DOMAIN,
    DOMAIN_STDLIB,
    APPLICATION_NO_FRAMEWORKS,
    ONLY_MAIN_WIRES,
) = CONTRACT_NAMES


def copy_project(destination: Path) -> Path:
    """Copia el código y la configuración de import-linter a `destination`."""
    shutil.copytree(
        BACKEND / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy(BACKEND / "pyproject.toml", destination / "pyproject.toml")
    return destination


def lint_imports(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LINT_IMPORTS)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


def broken_contracts(result: subprocess.CompletedProcess[str]) -> list[str]:
    """Nombres de los contratos rotos; la salida parte las líneas largas."""
    output = " ".join(result.stdout.split())
    return [name for name in CONTRACT_NAMES if f"{name} BROKEN" in output]


@pytest.mark.req("fase-1a:2.5")
def test_lint_imports_codigo_actual_cumple_los_contratos() -> None:
    result = lint_imports(BACKEND)

    assert result.returncode == 0, result.stdout
    assert broken_contracts(result) == []


@pytest.mark.req("fase-1a:2.5")
def test_lint_imports_copia_sin_violaciones_cumple_los_contratos(
    tmp_path: Path,
) -> None:
    project = copy_project(tmp_path)

    result = lint_imports(project)

    assert result.returncode == 0, result.stdout


@pytest.mark.req("fase-1a:2.5")
def test_lint_imports_cadena_api_application_domain_es_legitima(
    tmp_path: Path,
) -> None:
    project = copy_project(tmp_path)
    (project / "src" / "api" / "ok.py").write_text("import src.application\n")
    (project / "src" / "application" / "ok.py").write_text("import src.domain\n")

    result = lint_imports(project)

    assert result.returncode == 0, result.stdout


@pytest.mark.req("fase-1a:2.5")
def test_lint_imports_main_puede_importar_todas_las_capas_y_la_configuracion(
    tmp_path: Path,
) -> None:
    project = copy_project(tmp_path)
    main = project / "src" / "main.py"
    wiring = "".join(
        f"import src.{module}\n"
        for module in ("api", "application", "domain", "infrastructure", "config")
    )
    main.write_text(main.read_text("utf-8") + wiring, "utf-8")

    result = lint_imports(project)

    assert result.returncode == 0, result.stdout


@pytest.mark.req("fase-1a:2.5")
@pytest.mark.parametrize(
    ("layer", "imported", "contract"),
    [
        pytest.param("api", "src.infrastructure", LAYERS, id="api-infrastructure"),
        pytest.param("api", "src.domain", API_NOT_DOMAIN, id="api-domain"),
        pytest.param("infrastructure", "src.api", LAYERS, id="infrastructure-api"),
        pytest.param(
            "application", "src.infrastructure", LAYERS, id="application-infrastructure"
        ),
        pytest.param("application", "src.api", LAYERS, id="application-api"),
        pytest.param("domain", "src.application", LAYERS, id="domain-application"),
        pytest.param("domain", "fastapi", DOMAIN_STDLIB, id="domain-fastapi"),
        pytest.param("domain", "sqlalchemy", DOMAIN_STDLIB, id="domain-sqlalchemy"),
        pytest.param("domain", "boto3", DOMAIN_STDLIB, id="domain-boto3"),
        pytest.param(
            "application",
            "fastapi",
            APPLICATION_NO_FRAMEWORKS,
            id="application-fastapi",
        ),
        pytest.param(
            "application",
            "sqlalchemy",
            APPLICATION_NO_FRAMEWORKS,
            id="application-sqlalchemy",
        ),
        pytest.param(
            "application", "boto3", APPLICATION_NO_FRAMEWORKS, id="application-boto3"
        ),
        pytest.param("domain", "src.config", ONLY_MAIN_WIRES, id="domain-config"),
        pytest.param(
            "infrastructure", "src.config", ONLY_MAIN_WIRES, id="infrastructure-config"
        ),
        pytest.param("api", "src.config", ONLY_MAIN_WIRES, id="api-config"),
        pytest.param("application", "src.main", ONLY_MAIN_WIRES, id="application-main"),
        pytest.param("api", "src.main", ONLY_MAIN_WIRES, id="api-main"),
    ],
)
def test_lint_imports_importacion_prohibida_rompe_el_contrato(
    layer: str, imported: str, contract: str, tmp_path: Path
) -> None:
    project = copy_project(tmp_path)
    (project / "src" / layer / "violation.py").write_text(f"import {imported}\n")

    result = lint_imports(project)

    assert result.returncode != 0
    assert contract in broken_contracts(result), result.stdout
