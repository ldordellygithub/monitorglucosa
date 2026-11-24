"""Exporta de forma determinista `backend/openapi.json` y `docs/api/README.md`.

Uso:
    uv run --directory backend python tools/export_openapi.py
    uv run --directory backend python tools/export_openapi.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
OPENAPI_JSON_PATH = BACKEND_DIR / "openapi.json"
API_README_PATH = REPO_ROOT / "docs" / "api" / "README.md"
SPECS_DIR = REPO_ROOT / ".kiro" / "specs"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.config import Settings  # noqa: E402
from src.main import create_app  # noqa: E402

EXPORT_ENV: dict[str, str] = {
    "ENVIRONMENT": "local",
    "DATABASE_HOST": "localhost",
    "DATABASE_PORT": "5432",
    "DATABASE_NAME": "monitorglucosa",
    "DATABASE_USER": "mg_api",
    "DATABASE_PASSWORD": "export-placeholder",
    "LOCAL_JWT_ISSUER": "http://jwt-issuer:9000",
    "LOCAL_JWKS_URL": "http://jwt-issuer:9000/.well-known/jwks.json",
    "LOCAL_JWT_CLIENT_IDS": "web,collector",
}


def build_schema() -> dict[str, Any]:
    """Construye el contrato OpenAPI 3.1 desde `create_app()` en entorno aislado."""
    with mock.patch.dict(os.environ, EXPORT_ENV, clear=True):
        settings = Settings()
    app = create_app(settings)
    return app.openapi()


def render_openapi_json(schema: dict[str, Any]) -> str:
    """Serializa el esquema de forma determinista (claves ordenadas, 2 espacios)."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _resolve_ref(schema: dict[str, Any], node: Any) -> Any:
    """Resuelve un `$ref` interno (`#/components/...`) en un nivel."""
    if isinstance(node, dict) and "$ref" in node and isinstance(node["$ref"], str):
        ref = node["$ref"]
        if ref.startswith("#/"):
            target: Any = schema
            for part in ref[2:].split("/"):
                target = target[part]
            return target
    return node


def _format_security(security_list: list[dict[str, list[str]]] | None) -> str:
    if not security_list:
        return "Pública (sin autenticación)"
    names: list[str] = []
    for item in security_list:
        for scheme_name, scopes in item.items():
            if scopes:
                names.append(f"`{scheme_name}` ({', '.join(scopes)})")
            else:
                names.append(f"`{scheme_name}`")
    return " · ".join(names)


def _format_schema_summary(node: dict[str, Any]) -> str:
    if "$ref" in node and isinstance(node["$ref"], str):
        return f"`{node['$ref'].rsplit('/', maxsplit=1)[-1]}`"
    if "anyOf" in node and isinstance(node["anyOf"], list):
        parts = [_format_schema_summary(item) for item in node["anyOf"]]
        return " \\| ".join(parts)
    if "type" in node:
        return f"`{node['type']}`"
    return "`object`"


def _discover_spec_contracts(specs_dir: Path = SPECS_DIR) -> list[tuple[str, str]]:
    """Lista los contratos `openapi.yaml` de las specs en orden determinista."""
    if not specs_dir.exists():
        return []
    contracts: list[tuple[str, str]] = []
    for path in sorted(specs_dir.glob("*/openapi.yaml")):
        spec_name = path.parent.name
        rel_link = f"../../.kiro/specs/{spec_name}/openapi.yaml"
        contracts.append((spec_name, rel_link))
    return contracts


def render_api_readme(
    schema: dict[str, Any],
    specs_dir: Path = SPECS_DIR,
) -> str:
    """Genera `docs/api/README.md` en español desde `backend/openapi.json` (D17)."""
    info = schema.get("info", {})
    components = schema.get("components", {})
    lines: list[str] = [
        "<!-- Archivo generado por backend/tools/export_openapi.py. "
        "No editar a mano. -->",
        "",
        f"# {info.get('title', 'API')} (`v{info.get('version', '0.0.0')}`)",
        "",
        f"> {info.get('summary', '')}",
        "",
        "- **Contrato OpenAPI 3.1 (fuente de verdad):** "
        "[`backend/openapi.json`](../../backend/openapi.json)",
        "- **Swagger UI / ReDoc:** disponibles en `/docs` y `/redoc` en `local` y "
        "`test`; desactivados en `prod` (D17).",
        "",
    ]

    description = str(info.get("description", "")).strip()
    if description:
        lines.extend([description, ""])

    # Servidores
    servers = schema.get("servers", [])
    if servers:
        lines.extend(
            [
                "## Servidores",
                "",
                "| URL | Descripción |",
                "| --- | --- |",
            ]
        )
        for srv in servers:
            url = srv.get("url", "")
            desc = str(srv.get("description", "")).replace("\n", " ").strip()
            lines.append(f"| `{url}` | {desc} |")
        lines.append("")

    # Esquemas de seguridad
    sec_schemes = components.get("securitySchemes", {})
    if sec_schemes:
        lines.extend(
            [
                "## Esquemas de seguridad",
                "",
                "| Esquema | Tipo | Descripción |",
                "| --- | --- | --- |",
            ]
        )
        for name in sorted(sec_schemes):
            sec = sec_schemes[name]
            sec_type = sec.get("type", "")
            if sec.get("scheme"):
                sec_type = f"{sec_type} ({sec['scheme']})"
            desc = str(sec.get("description", "")).replace("\n", " ").strip()
            lines.append(f"| `{name}` | `{sec_type}` | {desc} |")
        lines.append("")

    # Índice de operaciones
    paths = schema.get("paths", {})
    lines.extend(
        [
            "## Operaciones",
            "",
            "| Operación | Método y ruta | Seguridad | Criterios | Resumen |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path in sorted(paths):
        path_item = paths[path]
        for method in sorted(path_item):
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            op = path_item[method]
            operations.append((path, method.upper(), op))
            op_id = op.get("operationId", "-")
            security_text = _format_security(op.get("security"))
            reqs = ", ".join(op.get("x-requirements", [])) or "—"
            summary = str(op.get("summary", "")).strip()
            lines.append(
                f"| `{op_id}` | `{method.upper()} {path}` | {security_text} "
                f"| {reqs} | {summary} |"
            )
    lines.append("")

    # Detalle de cada operación
    for path, method, op in operations:
        op_id = op.get("operationId", "")
        lines.extend(
            [
                f"### `{method} {path}` (`{op_id}`)",
                "",
                str(op.get("description", "")).strip(),
                "",
                f"- **Seguridad:** {_format_security(op.get('security'))}",
                f"- **Etiquetas:** {', '.join(op.get('tags', [])) or '—'}",
                f"- **Requisitos:** {', '.join(op.get('x-requirements', [])) or '—'}",
                "",
                "| Código | Esquema | Cabeceras | Descripción |",
                "| --- | --- | --- | --- |",
            ]
        )
        responses = op.get("responses", {})
        examples_blocks: list[tuple[str, str, Any]] = []
        for status_code in sorted(responses):
            resolved = _resolve_ref(schema, responses[status_code])
            desc = str(resolved.get("description", "")).replace("\n", " ").strip()
            headers = ", ".join(f"`{h}`" for h in sorted(resolved.get("headers", {})))
            headers = headers or "—"
            json_media = resolved.get("content", {}).get("application/json", {})
            schema_summary = (
                _format_schema_summary(json_media.get("schema", {}))
                if json_media
                else "—"
            )
            lines.append(f"| `{status_code}` | {schema_summary} | {headers} | {desc} |")
            if "example" in json_media:
                examples_blocks.append((status_code, "Ejemplo", json_media["example"]))
            elif "examples" in json_media:
                for ex_name in sorted(json_media["examples"]):
                    ex = json_media["examples"][ex_name]
                    label = ex.get("summary", ex_name)
                    examples_blocks.append((status_code, label, ex.get("value")))

        if examples_blocks:
            lines.extend(["", "**Ejemplos de respuesta:**", ""])
            for status_code, label, value in examples_blocks:
                rendered = json.dumps(value, indent=2, ensure_ascii=False)
                lines.extend(
                    [
                        f"- `{status_code}` — {label}:",
                        "",
                        "```json",
                        rendered,
                        "```",
                        "",
                    ]
                )
        else:
            lines.append("")

    # Catálogo de códigos de error
    error_code_schema = components.get("schemas", {}).get("ErrorCode", {})
    error_codes = error_code_schema.get("enum", [])
    if error_codes:
        lines.extend(
            [
                "## Catálogo de códigos de error (`ErrorCode`)",
                "",
                "Todas las respuestas de error generadas por la API usan `ErrorBody` "
                "(`code`, `message`, `details`) y nunca repiten valores de entrada:",
                "",
            ]
        )
        for code in error_codes:
            lines.append(f"- `{code}`")
        lines.append("")

    # Esquemas reutilizables
    schemas = components.get("schemas", {})
    if schemas:
        lines.extend(
            [
                "## Esquemas",
                "",
            ]
        )
        for name in sorted(schemas):
            schema_def = schemas[name]
            dumped = json.dumps(
                schema_def, indent=2, sort_keys=True, ensure_ascii=False
            )
            lines.extend(
                [
                    f"### `{name}`",
                    "",
                    "```json",
                    dumped,
                    "```",
                    "",
                ]
            )

    # Índice de contratos por spec
    spec_contracts = _discover_spec_contracts(specs_dir)
    lines.extend(
        [
            "## Índice de contratos por spec (`openapi.yaml`)",
            "",
            "| Spec | Contrato de diseño |",
            "| --- | --- |",
        ]
    )
    for spec_name, rel_link in spec_contracts:
        lines.append(f"| `{spec_name}` | [`openapi.yaml`]({rel_link}) |")
    lines.append("")

    return "\n".join(lines)


def check_artifacts(
    openapi_path: Path = OPENAPI_JSON_PATH,
    readme_path: Path = API_README_PATH,
    specs_dir: Path = SPECS_DIR,
) -> list[str]:
    """Comprueba que `openapi.json` y `docs/api/README.md` coinciden."""
    schema = build_schema()
    expected_json = render_openapi_json(schema)
    expected_readme = render_api_readme(schema, specs_dir=specs_dir)

    differences: list[str] = []
    if (
        not openapi_path.exists()
        or openapi_path.read_text(encoding="utf-8") != expected_json
    ):
        differences.append(str(openapi_path))
    if (
        not readme_path.exists()
        or readme_path.read_text(encoding="utf-8") != expected_readme
    ):
        differences.append(str(readme_path))
    return differences


def write_artifacts(
    openapi_path: Path = OPENAPI_JSON_PATH,
    readme_path: Path = API_README_PATH,
    specs_dir: Path = SPECS_DIR,
) -> None:
    """Genera y escribe `backend/openapi.json` y `docs/api/README.md`."""
    schema = build_schema()
    openapi_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    openapi_path.write_text(render_openapi_json(schema), encoding="utf-8")
    readme_path.write_text(
        render_api_readme(schema, specs_dir=specs_dir), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporta o verifica backend/openapi.json y docs/api/README.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Falla con código 1 si los archivos en disco difieren de lo generado.",
    )
    args = parser.parse_args(argv)

    if args.check:
        diffs = check_artifacts()
        if diffs:
            print(
                "ERROR: artefactos OpenAPI desactualizados: " + ", ".join(diffs),
                file=sys.stderr,
            )
            return 1
        print("OK: backend/openapi.json y docs/api/README.md están al día.")
        return 0

    write_artifacts()
    print(f"Generado: {OPENAPI_JSON_PATH}")
    print(f"Generado: {API_README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
