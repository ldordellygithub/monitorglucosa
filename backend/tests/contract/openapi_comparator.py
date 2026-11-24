"""Comparador de conformidad entre backend/openapi.json y los openapi.yaml de specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
IGNORED_SCHEMA_KEYS = frozenset(
    {"title", "description", "example", "examples", "default"}
)


def load_spec_contracts(specs_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """Carga en orden determinista todos los `.kiro/specs/*/openapi.yaml`."""
    contracts: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(specs_dir.glob("*/openapi.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            contracts.append((path.parent.name, raw))
    return contracts


def _resolve_pointer(root: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"Solo se admiten referencias locales en OpenAPI: {ref}")
    current: Any = root
    for token in ref[2:].split("/"):
        unescaped = token.replace("~1", "/").replace("~0", "~")
        current = current[unescaped]
    return current


def resolve_object(node: Any, root: dict[str, Any]) -> Any:
    """Resuelve un `$ref` de primer nivel (p. ej. respuestas o cabeceras)."""
    seen: set[str] = set()
    current = node
    while isinstance(current, dict) and "$ref" in current:
        ref = str(current["$ref"])
        if ref in seen:
            break
        seen.add(ref)
        current = _resolve_pointer(root, ref)
    return current


def _canonical_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def normalize_schema(
    node: Any,
    root: dict[str, Any],
    *,
    _seen: frozenset[str] = frozenset(),
) -> Any:
    """Normaliza un JSON Schema resolviendo `$ref` y omitiendo metadatos textuales."""
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            ref = node["$ref"]
            if ref in _seen:
                return {"$circular": ref}
            target = _resolve_pointer(root, ref)
            return normalize_schema(target, root, _seen=_seen | {ref})

        normalized: dict[str, Any] = {}
        for key, value in node.items():
            if key in IGNORED_SCHEMA_KEYS:
                continue
            if key == "required" and isinstance(value, list):
                normalized[key] = sorted(value)
            elif key in {"anyOf", "oneOf"} and isinstance(value, list):
                items = [normalize_schema(item, root, _seen=_seen) for item in value]
                normalized[key] = sorted(items, key=_canonical_key)
            elif key == "enum" and isinstance(value, list):
                normalized[key] = sorted(value, key=_canonical_key)
            elif key == "properties" and isinstance(value, dict):
                normalized[key] = {
                    prop_name: normalize_schema(prop_schema, root, _seen=_seen)
                    for prop_name, prop_schema in sorted(value.items())
                }
            else:
                normalized[key] = normalize_schema(value, root, _seen=_seen)
        return normalized

    if isinstance(node, list):
        return [normalize_schema(item, root, _seen=_seen) for item in node]

    return node


def _normalize_security(security: Any) -> list[dict[str, list[str]]]:
    if not security:
        return []
    normalized = [
        {name: sorted(scopes) for name, scopes in sorted(entry.items())}
        for entry in security
        if isinstance(entry, dict)
    ]
    return sorted(normalized, key=_canonical_key)


def _normalize_responses(
    responses: dict[str, Any], root: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for code, raw_resp in responses.items():
        resp = resolve_object(raw_resp, root)
        if not isinstance(resp, dict):
            continue
        headers: dict[str, Any] = {}
        for header_name, raw_header in resp.get("headers", {}).items():
            resolved_header = resolve_object(raw_header, root)
            if isinstance(resolved_header, dict):
                headers[header_name.lower()] = normalize_schema(
                    resolved_header.get("schema", {}), root
                )

        content: dict[str, Any] = {}
        for media_type, media_obj in resp.get("content", {}).items():
            if isinstance(media_obj, dict) and "schema" in media_obj:
                content[media_type] = normalize_schema(media_obj["schema"], root)

        result[str(code)] = {"headers": headers, "content": content}
    return result


def _extract_operations(
    doc: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    ops: dict[tuple[str, str], dict[str, Any]] = {}
    for path, path_item in doc.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            ops[(path, method.lower())] = {
                "operationId": operation.get("operationId"),
                "security": _normalize_security(operation.get("security")),
                "responses": _normalize_responses(operation.get("responses", {}), doc),
            }
    return ops


def compare_contracts(
    generated: dict[str, Any],
    spec_docs: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    """Compara el OpenAPI generado contra la unión de los `openapi.yaml` de specs."""
    expected_ops: dict[tuple[str, str], dict[str, Any]] = {}
    for _spec_name, doc in spec_docs:
        expected_ops.update(_extract_operations(doc))

    actual_ops = _extract_operations(generated)
    differences: list[str] = []

    for key in sorted(expected_ops):
        path, method = key
        label = f"{method.upper()} {path}"
        if key not in actual_ops:
            differences.append(f"Falta la operación {label} en backend/openapi.json")
            continue

        exp = expected_ops[key]
        act = actual_ops[key]

        if exp["operationId"] != act["operationId"]:
            differences.append(
                f"{label}: operationId esperado {exp['operationId']!r}, "
                f"obtenido {act['operationId']!r}"
            )
        if exp["security"] != act["security"]:
            differences.append(
                f"{label}: security esperado {exp['security']!r}, "
                f"obtenido {act['security']!r}"
            )

        exp_codes = set(exp["responses"])
        act_codes = set(act["responses"])
        if exp_codes != act_codes:
            differences.append(
                f"{label}: códigos de respuesta esperados {sorted(exp_codes)}, "
                f"obtenidos {sorted(act_codes)}"
            )
            continue

        for code in sorted(exp_codes):
            exp_resp = exp["responses"][code]
            act_resp = act["responses"][code]
            if exp_resp["headers"] != act_resp["headers"]:
                differences.append(
                    f"{label} [{code}]: cabeceras difieren "
                    f"(esperado {exp_resp['headers']!r}, "
                    f"obtenido {act_resp['headers']!r})"
                )
            if exp_resp["content"] != act_resp["content"]:
                differences.append(
                    f"{label} [{code}]: esquema de cuerpo difiere "
                    f"(esperado {exp_resp['content']!r}, "
                    f"obtenido {act_resp['content']!r})"
                )

    for key in sorted(set(actual_ops) - set(expected_ops)):
        path, method = key
        differences.append(
            f"Operación no documentada en ninguna spec: {method.upper()} {path}"
        )

    return differences
