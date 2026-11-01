#!/usr/bin/env python3
"""Valida la estructura y la trazabilidad de una spec estilo Kiro.

Uso: python3 lint.py .kiro/specs/<feature>
Salida: 0 sin errores, 1 con errores, 2 por uso incorrecto.
Solo usa la biblioteca estándar.
"""
import re
import sys
from pathlib import Path

DESIGN_SECTIONS = [
    "Overview",
    "Architecture",
    "Components and Interfaces",
    "Data Models",
    "Error Handling",
    "Testing Strategy",
    "Decisions",
    "Requirements Traceability",
]
EARS_START = re.compile(r"\b(WHEN|IF|WHILE|WHERE|THE SYSTEM)\b", re.IGNORECASE)
TASK_LINE = re.compile(r"^\s*- \[( |x|X)\](\*?)\s+(.*)$")
REQ_REF = re.compile(r"_Requirements?:\s*([^_]+)_")
REQ_HEADING = re.compile(r"^###\s+Requirement\s+(\d+)\b")
CRITERION = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
ARCH_VIEWS = re.compile(r"^#{2,3}\s+Architecture Views\b(.*?)(?=^#{1,3}\s|\Z)", re.MULTILINE | re.DOTALL)
NO_CHANGES = re.compile(r"sin cambios|no changes", re.IGNORECASE)
ADR_MARK = re.compile(r"(→|->)\s*ADR\b")
TRACE_SECTION = re.compile(r"^##\s+Requirements Traceability\b(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
TRACE_ID = re.compile(r"NFR[\s-]?\d+|NFR\b|\d+(?:\.\d+)?", re.IGNORECASE)
NFR_REF = re.compile(r"^NFR[\s-]?(\d+)$", re.IGNORECASE)
PENDING = re.compile(r"<pendiente\b[^>\n]*>", re.IGNORECASE)


def normalize_ref(ref):
    """'NFR 1', 'nfr1' o 'NFR-1' -> 'NFR-1' (requisito no funcional); el resto queda igual."""
    nfr = NFR_REF.match(ref)
    return f"NFR-{nfr.group(1)}" if nfr else ref


def parse_requirements(text):
    """Devuelve (set de 'N', 'N.M' y 'NFR-N', lista de criterios sin SHALL o sin patrón EARS)."""
    ids, problems = set(), []
    current = None
    in_criteria = in_nfr = False
    for line in text.splitlines():
        heading = REQ_HEADING.match(line)
        if heading:
            current = heading.group(1)
            ids.add(current)
            in_criteria = in_nfr = False
            continue
        if line.startswith("## "):
            current = None
            in_criteria = False
            in_nfr = line.strip().lower().startswith("## non-functional")
            continue
        if in_nfr:
            nfr = CRITERION.match(line)
            if nfr:
                ids.add(f"NFR-{nfr.group(1)}")
            continue
        if line.startswith("#### Acceptance Criteria"):
            in_criteria = True
            continue
        if current and in_criteria:
            crit = CRITERION.match(line)
            if crit:
                ids.add(f"{current}.{crit.group(1)}")
                body = crit.group(2)
                if "SHALL" not in body.upper() or not EARS_START.search(body):
                    problems.append(f"{current}.{crit.group(1)}: {body[:70]}")
    return ids, problems



def check_architecture(design_text, tasks_text, closed):
    """Documentación arquitectónica: 'Architecture Views' en el diseño y sus tareas (diagramas y ADR)."""
    errors, warnings = [], []
    match = ARCH_VIEWS.search(design_text)
    if match is None:
        problem = "design.md no tiene la sección 'Architecture Views' (escribe «Sin cambios» si no aplica)"
        (warnings if closed else errors).append(problem)
    else:
        body = re.sub(r"<[^>]*>", "", match.group(1)).strip()
        if not body:
            errors.append("'Architecture Views' está vacía: lista las vistas afectadas o escribe «Sin cambios»")
        elif (not NO_CHANGES.search(body) and tasks_text is not None
              and not re.search(r"docs/architecture|diagram", tasks_text, re.IGNORECASE)):
            errors.append("design.md lista vistas en 'Architecture Views', pero tasks.md no tiene la tarea que "
                          "actualiza docs/architecture")
    if tasks_text is not None and ADR_MARK.search(design_text) and not re.search(r"\bADR\b", tasks_text):
        errors.append("design.md marca decisiones «→ ADR», pero tasks.md no tiene la tarea que las registra")
    return errors, warnings


def check_traceability(design_text, req_ids, closed):
    """Tabla 'Requirements Traceability': columna Decisiones y una fila por requisito (fuente de la matriz)."""
    match = TRACE_SECTION.search(design_text)
    if match is None or not req_ids:
        return [], []  # la sección ausente ya la informa DESIGN_SECTIONS
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in match.group(1).splitlines() if line.strip().startswith("|")]
    rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r if c)]
    problems, warnings, cited = [], [], set()
    if not rows or not any("decisi" in c.lower() for c in rows[0]):
        problems.append("'Requirements Traceability' no tiene la columna Decisiones (D1, ADR NNNN, T-n o «—»)")
    for cells in rows[1:]:
        for ref in (normalize_ref(r.upper()) for r in TRACE_ID.findall(cells[0])):
            if ref == "NFR":
                cited |= {i for i in req_ids if i.startswith("NFR-")}
                continue
            if ref not in req_ids:
                problems.append(f"'Requirements Traceability' cita '{ref}', que no existe en requirements.md")
            cited.add(ref.split(".")[0])
    for req in sorted((i for i in req_ids if i.isdigit()), key=int):
        if req not in cited:
            problems.append(f"El requisito {req} no tiene fila en 'Requirements Traceability'")
    for nfr in sorted(i for i in req_ids if i.startswith("NFR-") and i not in cited):
        warnings.append(f"{nfr} no tiene fila en 'Requirements Traceability' (usa NFR-N o «NFR» para todos)")
    return ([], problems + warnings) if closed else (problems, warnings)


def main():
    if len(sys.argv) != 2:
        print("Uso: python3 lint.py .kiro/specs/<feature>")
        return 2
    spec = Path(sys.argv[1])
    if not spec.is_dir():
        print(f"ERROR: no existe la carpeta {spec}")
        return 2

    errors, warnings = [], []
    req_file, bug_file = spec / "requirements.md", spec / "bugfix.md"
    design_file, tasks_file = spec / "design.md", spec / "tasks.md"

    base = req_file if req_file.exists() else bug_file if bug_file.exists() else None
    if base is None:
        errors.append("Falta requirements.md (o bugfix.md)")

    req_ids = set()
    if base is not None:
        pending = PENDING.findall(base.read_text(encoding="utf-8"))
        if pending:
            warnings.append(f"{base.name} tiene {len(pending)} <pendiente> sin resolver: {', '.join(pending[:3])}")
    if base is req_file:
        req_ids, ears_problems = parse_requirements(req_file.read_text(encoding="utf-8"))
        if not any("." not in i for i in req_ids):
            errors.append("requirements.md no tiene ningún '### Requirement N'")
        for problem in ears_problems:
            warnings.append(f"Criterio sin formato EARS (falta SHALL o patrón): {problem}")
    elif base is bug_file:
        text = bug_file.read_text(encoding="utf-8")
        for section in ("Reproduction", "Current Behavior", "Expected Behavior", "Unchanged Behavior"):
            if section.lower() not in text.lower():
                errors.append(f"bugfix.md no tiene la sección '{section}'")

    if design_file.exists():
        text = design_file.read_text(encoding="utf-8")
        for section in DESIGN_SECTIONS:
            if not re.search(rf"^##\s+{re.escape(section)}\b", text, re.MULTILINE):
                errors.append(f"design.md no tiene la sección '## {section}'")
        if "```mermaid" not in text:
            warnings.append("design.md no tiene ningún diagrama Mermaid")
        if "<" in text and re.search(r"<(pendiente|componente|título)[^>]*>", text, re.IGNORECASE):
            warnings.append("design.md aún tiene marcadores de plantilla sin rellenar")
    elif tasks_file.exists():
        errors.append("Hay tasks.md pero no design.md")

    done = total = 0
    if tasks_file.exists():
        covered = set()
        for number, line in enumerate(tasks_file.read_text(encoding="utf-8").splitlines(), 1):
            match = TASK_LINE.match(line)
            if match:
                total += 1
                done += match.group(1).lower() == "x"
        text = tasks_file.read_text(encoding="utf-8")
        refs = REQ_REF.findall(text)
        for group in refs:
            for ref in (normalize_ref(r.strip()) for r in group.split(",")):
                if not ref:
                    continue
                if req_ids and ref not in req_ids:
                    errors.append(f"tasks.md cita el requisito '{ref}', que no existe en requirements.md")
                covered.add(ref)
                covered.add(ref.split(".")[0])
        if total == 0:
            errors.append("tasks.md no tiene ninguna tarea con casilla '- [ ]'")
        if req_ids:
            for req in sorted((i for i in req_ids if i.isdigit()), key=int):
                if req not in covered:
                    errors.append(f"El requisito {req} no está cubierto por ninguna tarea")
        # tareas de primer nivel sin referencia: se avisa, salvo los checkpoints
        no_ref_blocks = 0
        blocks = re.split(r"\n(?=- \[[ xX]\]\*? )", text)
        for block in blocks:
            head = block.splitlines()[0] if block.strip() else ""
            if TASK_LINE.match(head) and "checkpoint" not in head.lower() and not REQ_REF.search(block):
                no_ref_blocks += 1
        if no_ref_blocks:
            warnings.append(f"{no_ref_blocks} tarea(s) de primer nivel sin '_Requirements: X.Y_'")

    if design_file.exists():
        tasks_text = tasks_file.read_text(encoding="utf-8") if tasks_file.exists() else None
        arch_errors, arch_warnings = check_architecture(design_file.read_text(encoding="utf-8"), tasks_text,
                                                        closed=bool(total) and done == total)
        errors += arch_errors
        warnings += arch_warnings
        trace_errors, trace_warnings = check_traceability(design_file.read_text(encoding="utf-8"), req_ids,
                                                          closed=bool(total) and done == total)
        errors += trace_errors
        warnings += trace_warnings

    print(f"Spec: {spec}")
    if total:
        print(f"Progreso de tareas: {done}/{total}")
    for item in errors:
        print(f"ERROR  {item}")
    for item in warnings:
        print(f"AVISO  {item}")
    if not errors and not warnings:
        print("OK: sin problemas")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
