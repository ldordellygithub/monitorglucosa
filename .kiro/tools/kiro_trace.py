#!/usr/bin/env python3
"""Matriz de trazabilidad del flujo estilo Kiro: requisitos ↔ componentes ↔ decisiones ↔ tareas ↔ pruebas.

Lee .kiro/specs/*/ (requirements.md, design.md, tasks.md y manual-checks.md) y las etiquetas de las pruebas, y
genera docs/traceability.md. Solo usa la biblioteca estándar: se copia al proyecto (.kiro/tools/kiro_trace.py)
para que CI lo compruebe sin el kit.

Etiquetas: prefijo único del nombre de la spec + criterio (N.M o NFR-N).
  Python:      @pytest.mark.req("fase-1b:2.1", "fase-1b:NFR-1")
  TS, JS y sh: test("[req fase-1b:2.1] guarda el lote", ...)   o un comentario   # [req fase-1b:2.1]
Verificación manual: .kiro/specs/<spec>/manual-checks.md con líneas   - 2.3: cómo se verifica · evidencia

Commits: el trailer `Refs: <spec>#<tarea>` (p. ej. Refs: fase-1b#2.1) enlaza cada commit con su tarea. No van en
la matriz commiteada (no puede contener el SHA del commit que la incluye): se ven con `commits`.

Uso:
  python3 kiro_trace.py generate [raíz]   escribe docs/traceability.md
  python3 kiro_trace.py check    [raíz]   falla si la matriz está desactualizada, si hay pruebas huérfanas o si
                                          una spec cerrada tiene criterios sin prueba ni verificación manual
  python3 kiro_trace.py commits  [raíz] [--spec prefijo]   criterio → tareas → commits (Markdown por stdout)
Salida: 0 sin errores, 1 con errores, 2 por uso incorrecto. La raíz por defecto es la carpeta actual.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

MATRIX = Path("docs") / "traceability.md"
SPECS = Path(".kiro") / "specs"
SCAN_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh"}
TOP_SKIP = {".git", ".kiro", "docs"}  # el kit y los ejemplos de documentación no son pruebas
ANY_SKIP = {"node_modules", ".venv", "venv", "__pycache__", ".next", ".tox", "site-packages"}
MAX_BYTES = 1_000_000
NAME_LOOKAHEAD = 60

REQ_HEADING = re.compile(r"^###\s+Requirement\s+(\d+)\b[\s:.—–-]*(.*?)\s*$")
CRITERION = re.compile(r"^\s*(\d+)\.\s+\S")
USER_STORY = re.compile(r"I want (?:to )?(.+?)(?:,\s*so that\b|$)", re.IGNORECASE)
TASK = re.compile(r"^\s*- \[( |x|X)\](\*?)\s+(?:(\d+(?:\.\d+)*)\.?\s+)?")
REQ_REF = re.compile(r"_Requirements?:\s*([^_]+)_")
TRACE_SECTION = re.compile(r"^##\s+Requirements Traceability\b(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
TRACE_ID = re.compile(r"NFR[\s-]?\d+|NFR\b|\d+(?:\.\d+)?", re.IGNORECASE)
SEPARATOR = re.compile(r":?-+:?")
DESIGN_DECISION = re.compile(r"^###\s+(D\d+)\b", re.MULTILINE)
DECISION_REF = re.compile(r"\b(D\d+|ADR[\s-]?\d{1,4}|[TP]-\d+)\b")
PY_MARK = re.compile(r"pytest\.mark\.req\(([^)]*)\)")
PY_STRING = re.compile(r"""["']([^"'\n]*)["']""")
TAG = re.compile(r"\[req\s+([^\]\n]+)\]")
TAG_REF = re.compile(r"^([a-z0-9][a-z0-9-]*):(\d+\.\d+|NFR[\s-]?\d+)$", re.IGNORECASE)
PY_NAME = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")
JS_TITLE = re.compile(r"""\b(?:it|test|describe)(?:\.\w+)*\(\s*(["'`])(.*?)\1""")
MANUAL = re.compile(r"^\s*[-*]\s+(\d+\.\d+|NFR[\s-]?\d+)\s*:\s*(\S.*?)\s*$", re.IGNORECASE)
PLACEHOLDER = re.compile(r"<[^>\n]+>")
NFR = re.compile(r"^NFR[\s-]?(\d+)$", re.IGNORECASE)
PHASE = re.compile(r"^fase-(\d+)")
TRAILER_REF = re.compile(r"^([a-z0-9][a-z0-9-]*)#(\d+(?:\.\d+)*)$", re.IGNORECASE)
LOG_FORMAT = "%h%x1f%s%x1f%(trailers:key=Refs,valueonly,separator=%x1f)%x1e"
LEGEND = ("Estado: ✅ prueba etiquetada y tareas hechas · 📝 verificación manual justificada y tareas hechas · "
          "⚠️ falta la prueba o la tarea · ❌ sin prueba ni tarea hecha. Tareas: ✓ hecha · ○ pendiente.")


@dataclass
class Finding:
    level: str  # "ERROR" o "AVISO"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}  {self.where}: {self.message}"


@dataclass(frozen=True)
class Task:
    tid: str
    done: bool
    optional: bool


@dataclass
class Criterion:
    cid: str  # '2.1' o 'NFR-1'
    req: str  # '2' o 'NFR'
    components: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    tests: set[str] = field(default_factory=set)
    manual: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return bool(self.tests or self.manual)

    @property
    def tasks_done(self) -> bool:
        """Hecho si lo están todas las tareas obligatorias que lo citan (o alguna opcional, si no hay obligatorias)."""
        required = [t for t in self.tasks if not t.optional]
        if required:
            return all(t.done for t in required)
        return any(t.done for t in self.tasks)

    @property
    def state(self) -> str:
        if self.verified and self.tasks_done:
            return "✅" if self.tests else "📝"
        return "⚠️" if self.verified or self.tasks_done else "❌"


@dataclass
class Spec:
    name: str
    titles: dict[str, str]
    criteria: dict[str, Criterion]
    decision_ids: set[str]
    done: int = 0
    total: int = 0

    @property
    def closed(self) -> bool:
        return self.total > 0 and self.done == self.total

    @property
    def phase(self) -> str:
        match = PHASE.match(self.name)
        return match.group(1) if match else "—"

    @property
    def verified(self) -> int:
        return sum(c.verified for c in self.criteria.values())

    @property
    def state(self) -> str:
        return "cerrada" if self.closed else "en curso" if self.total else "sin tareas"


@dataclass(frozen=True)
class Orphan:
    where: str
    tag: str
    problem: str


@dataclass
class Project:
    root: Path
    specs: list[Spec]
    bugfixes: list[str]
    orphans: list[Orphan]
    findings: list[Finding]


# ------------------------------------------------------------------ lectura de las specs
def normalize(ref: str) -> str:
    """'NFR 1', 'nfr1' o 'NFR-1' -> 'NFR-1'; 'nfr' -> 'NFR'; el resto queda igual."""
    ref = ref.strip()
    nfr = NFR.match(ref)
    if nfr:
        return f"NFR-{nfr.group(1)}"
    return "NFR" if ref.upper() == "NFR" else ref


def parse_requirements(text: str) -> tuple[dict[str, str], list[str]]:
    """Títulos por requisito y criterios en orden ('N.M' y 'NFR-N'), con las mismas reglas que el linter."""
    titles: dict[str, str] = {}
    ids: list[str] = []
    current, in_criteria, in_nfr = None, False, False
    for line in text.splitlines():
        heading = REQ_HEADING.match(line)
        if heading:
            current, in_criteria, in_nfr = heading.group(1), False, False
            titles[current] = heading.group(2)[:60]
            continue
        if line.startswith("## "):
            current, in_criteria = None, False
            in_nfr = line.strip().lower().startswith("## non-functional")
            continue
        number = CRITERION.match(line)
        story = USER_STORY.search(line) if current and not titles[current] and "User Story" in line else None
        if in_nfr and number:
            ids.append(f"NFR-{number.group(1)}")
        elif line.startswith("#### Acceptance Criteria"):
            in_criteria = True
        elif current and story:
            titles[current] = story.group(1).strip().rstrip(".")[:60]
        elif current and in_criteria and number:
            ids.append(f"{current}.{number.group(1)}")
    if any(i.startswith("NFR-") for i in ids):
        titles["NFR"] = "No funcionales"
    return titles, ids


def split_row(line: str) -> list[str]:
    cells = line.strip().replace("\\|", "\0").strip("|").split("|")
    return [c.replace("\0", "\\|").strip() for c in cells]


def parse_trace_table(text: str) -> list[tuple[list[str], str, str]]:
    """Filas de 'Requirements Traceability': (IDs de requisito o criterio, componentes, decisiones)."""
    match = TRACE_SECTION.search(text)
    if match is None:
        return []
    rows = [split_row(line) for line in match.group(1).splitlines() if line.strip().startswith("|")]
    rows = [r for r in rows if not all(SEPARATOR.fullmatch(c) for c in r if c)]
    if not rows:
        return []
    header = [c.lower() for c in rows[0]]
    comp = next((i for i, c in enumerate(header) if "component" in c), 1)
    dec = next((i for i, c in enumerate(header) if "decisi" in c), None)
    table = []
    for cells in rows[1:]:
        ids = [normalize(i) for i in TRACE_ID.findall(cells[0])]
        components = cells[comp] if comp < len(cells) else ""
        decisions = cells[dec] if dec is not None and dec < len(cells) else ""
        table.append((ids, components, decisions))
    return table


def parse_tasks(text: str) -> list[tuple[Task, list[str]]]:
    """Cada tarea (también las subtareas) con los requisitos que cita en su `_Requirements:`."""
    tasks: list[tuple[Task, list[str]]] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = TASK.match(line)
        if match:
            task = Task(match.group(3) or f"línea {number}", match.group(1).lower() == "x", match.group(2) == "*")
            tasks.append((task, []))
        for group in REQ_REF.findall(line):
            if tasks:
                tasks[-1][1].extend(normalize(r) for r in group.split(",") if r.strip())
    return tasks


def targets(criteria: dict[str, Criterion], ref: str) -> list[Criterion]:
    """Criterios a los que se refiere un ID: '2' (todo el requisito), '2.1', 'NFR-1' o 'NFR' (todos)."""
    if ref in criteria:
        return [criteria[ref]]
    return [c for c in criteria.values() if c.req == ref]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def load_spec(folder: Path) -> Spec:
    titles, ids = parse_requirements(read(folder / "requirements.md"))
    criteria = {cid: Criterion(cid, "NFR" if cid.startswith("NFR-") else cid.split(".")[0]) for cid in ids}
    design = read(folder / "design.md")
    for refs, components, decisions in parse_trace_table(design):
        for ref in refs:
            for crit in targets(criteria, ref):
                if components and components not in crit.components:
                    crit.components.append(components)
                if decisions and decisions not in crit.decisions:
                    crit.decisions.append(decisions)
    tasks = parse_tasks(read(folder / "tasks.md"))
    for task, refs in tasks:
        for ref in refs:
            for crit in targets(criteria, ref):
                if task not in crit.tasks:
                    crit.tasks.append(task)
    spec = Spec(folder.name, titles, criteria, set(DESIGN_DECISION.findall(design)))
    spec.total, spec.done = len(tasks), sum(t.done for t, _ in tasks)
    return spec


def load_specs(root: Path) -> tuple[list[Spec], list[str]]:
    folder = root / SPECS
    if not folder.is_dir():
        return [], []
    specs, bugfixes = [], []
    for spec in sorted(d for d in folder.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))):
        if (spec / "requirements.md").exists():
            specs.append(load_spec(spec))
        elif (spec / "bugfix.md").exists():
            bugfixes.append(spec.name)
    return specs, bugfixes


# ------------------------------------------------------------------ etiquetas de las pruebas
def project_files(root: Path) -> list[str]:
    """Archivos que git versionaría (respeta .gitignore); sin git, recorre la carpeta."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                             capture_output=True, timeout=30, check=True).stdout.decode("utf-8", "replace")
        files = [f for f in out.split("\0") if f]
    except (OSError, subprocess.SubprocessError):
        files = []
        for base, dirs, names in os.walk(root):
            rel = Path(base).relative_to(root)
            dirs[:] = [d for d in dirs if d not in ANY_SKIP and not (rel == Path(".") and d in TOP_SKIP)]
            files += [(rel / n).as_posix() for n in names]
    return sorted({f for f in files if wanted(f) and (root / f).is_file()})


def wanted(rel: str) -> bool:
    parts = Path(rel).parts
    return (Path(rel).suffix in SCAN_EXT and parts[0] not in TOP_SKIP
            and not any(p in ANY_SKIP for p in parts[:-1]))


def following_name(lines: list[str], start: int) -> str:
    for line in lines[start + 1:start + 1 + NAME_LOOKAHEAD]:
        match = PY_NAME.match(line)
        if match:
            return match.group(1)
    return ""


def scan_text(rel: str, text: str) -> list[tuple[int, str, str]]:
    """Etiquetas de un archivo: (línea, nombre de la prueba o '' si cubre el archivo, referencia)."""
    found = []
    lines = text.splitlines()
    for match in PY_MARK.finditer(text):
        index = text.count("\n", 0, match.start())
        decorator = lines[index].lstrip().startswith("@")  # pytestmark = ... cubre todo el módulo
        name = following_name(lines, index) if decorator else ""
        found += [(index + 1, name, ref) for ref in PY_STRING.findall(match.group(1))]
    for number, line in enumerate(lines):
        for match in TAG.finditer(line):
            title = JS_TITLE.search(line)
            if title:
                name = " ".join(TAG.sub("", title.group(2)).split())
            else:
                name = following_name(lines, number) if rel.endswith(".py") else ""
            found += [(number + 1, name, ref) for ref in re.split(r"[,\s]+", match.group(1).strip()) if ref]
    return found


def find_spec(prefix: str, specs: list[Spec]) -> Spec | str:
    """Spec cuyo nombre es el prefijo o empieza por «prefijo-», o el problema si no hay una sola."""
    prefix = prefix.lower()
    candidates = [s for s in specs if s.name == prefix] or [s for s in specs if s.name.startswith(prefix + "-")]
    if not candidates:
        return f"no hay ninguna spec con requisitos «{prefix}» ni «{prefix}-…» (el prefijo acaba en un guion)"
    if len(candidates) > 1:
        return f"el prefijo «{prefix}» es ambiguo: {', '.join(s.name for s in candidates)}"
    return candidates[0]


def resolve(ref: str, specs: list[Spec]) -> tuple[Spec, str] | str:
    """Spec y criterio de una referencia 'prefijo:N.M', o el problema si no apunta a ningún criterio."""
    match = TAG_REF.match(ref.strip())
    if not match:
        return "etiqueta mal formada: usa «spec:N.M» o «spec:NFR-N» (un criterio, no un requisito)"
    spec, cid = find_spec(match.group(1), specs), normalize(match.group(2))
    if isinstance(spec, str):
        return spec
    if cid not in spec.criteria:
        return f"{spec.name} no tiene el criterio {cid}"
    return spec, cid


def link_tests(root: Path, specs: list[Spec]) -> list[Orphan]:
    orphans = []
    for rel in project_files(root):
        path = root / rel
        if path.stat().st_size > MAX_BYTES:
            continue
        for line, name, ref in scan_text(rel, path.read_text(encoding="utf-8", errors="replace")):
            target = resolve(ref, specs)
            if isinstance(target, str):
                orphans.append(Orphan(f"{rel}:{line}", ref, target))
            else:
                target[0].criteria[target[1]].tests.add(f"{rel}::{name}" if name else rel)
    return orphans


def link_manual(root: Path, specs: list[Spec]) -> tuple[list[Orphan], list[Finding]]:
    orphans, findings = [], []
    for spec in specs:
        rel = (SPECS / spec.name / "manual-checks.md").as_posix()
        for number, line in enumerate(read(root / rel).splitlines(), 1):
            match = MANUAL.match(line)
            if not match:
                continue
            cid, how = normalize(match.group(1)), match.group(2)
            if cid not in spec.criteria:
                orphans.append(Orphan(f"{rel}:{number}", cid, f"{spec.name} no tiene el criterio {cid}"))
            elif PLACEHOLDER.search(how):
                findings.append(Finding("ERROR" if spec.closed else "AVISO", f"{rel}:{number}",
                                        f"la verificación manual de {cid} tiene marcadores sin rellenar"))
            else:
                spec.criteria[cid].manual.append(how)
    return orphans, findings


# ------------------------------------------------------------------ decisiones citadas
def steering_ids(root: Path) -> set[str]:
    """IDs T-n y P-n definidos en las tablas de decisiones del steering."""
    ids: set[str] = set()
    for path in sorted((root / ".kiro" / "steering").glob("*.md")):
        ids |= set(re.findall(r"^\|\s*([TP]-\d+)\s*\|", read(path), re.MULTILINE))
    return ids


def adr_numbers(root: Path) -> set[int]:
    folder = root / "docs" / "adr"
    return {int(p.name[:4]) for p in folder.glob("[0-9][0-9][0-9][0-9]-*.md")} if folder.is_dir() else set()


def check_decisions(root: Path, specs: list[Spec]) -> list[Finding]:
    """Cada decisión citada en la matriz existe: Dn en design.md, ADR en docs/adr y T-n/P-n en el steering."""
    findings = []
    known_steering, known_adr = steering_ids(root), adr_numbers(root)
    for spec in specs:
        cited = {ref for c in spec.criteria.values() for cell in c.decisions for ref in DECISION_REF.findall(cell)}
        for ref in sorted(cited):
            if ref.startswith("ADR"):
                missing = int(re.sub(r"\D", "", ref)) not in known_adr
                where = "docs/adr"
            elif ref.startswith("D"):
                missing, where = ref not in spec.decision_ids, "su design.md"
            else:
                missing, where = ref not in known_steering, "el steering"
            if missing:  # un «→ ADR» aún sin registrar es normal mientras la spec está abierta
                findings.append(Finding("ERROR" if spec.closed else "AVISO", spec.name,
                                        f"la matriz cita la decisión {ref}, que no existe en {where}"))
    return findings


def collect(root: Path) -> Project:
    specs, bugfixes = load_specs(root)
    orphans = link_tests(root, specs)
    manual_orphans, findings = link_manual(root, specs)
    return Project(root, specs, bugfixes, orphans + manual_orphans, findings + check_decisions(root, specs))


# ------------------------------------------------------------------ generación de la matriz
def pct(part: int, total: int) -> str:
    return f"{100 * part // total} %" if total else "—"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\\\\|", "\\|").replace("\n", " ") or "—"


def summary_lines(project: Project) -> list[str]:
    lines = ["## Resumen", "", "| Fase | Spec | Estado | Criterios | Con prueba | Manuales | Sin verificar | Cobertura |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for spec in project.specs:
        crits = list(spec.criteria.values())
        tests, manual = sum(bool(c.tests) for c in crits), sum(bool(c.manual) and not c.tests for c in crits)
        lines.append(f"| {spec.phase} | [{spec.name}](#{spec.name}) | {spec.state} | {len(crits)} | {tests} | "
                     f"{manual} | {len(crits) - spec.verified} | {pct(spec.verified, len(crits))} |")
    phases = sorted({s.phase for s in project.specs if s.phase != "—"}, key=int)
    if phases:
        lines += ["", "| Fase | Specs | Criterios verificados |", "| --- | --- | --- |"]
        for phase in phases:
            group = [s for s in project.specs if s.phase == phase]
            total, verified = sum(len(s.criteria) for s in group), sum(s.verified for s in group)
            lines.append(f"| {phase} | {len(group)} | {verified}/{total} ({pct(verified, total)}) |")
    if project.bugfixes:
        lines += ["", "Specs de bugfix (sin requirements.md), fuera de la matriz: " + ", ".join(project.bugfixes)]
    return lines + [""]


def task_cell(tasks: list[Task]) -> str:
    return ", ".join(f"{t.tid}{'*' if t.optional else ''} {'✓' if t.done else '○'}" for t in tasks) or "—"


def evidence_cell(crit: Criterion) -> str:
    items = [f"`{t}`" for t in sorted(crit.tests)] + [f"📝 {m}" for m in crit.manual]
    return "<br>".join(cell(i) for i in items) or "—"


def spec_lines(spec: Spec) -> list[str]:
    base = f"../{SPECS.as_posix()}/{spec.name}"
    links = (f"[Requisitos]({base}/requirements.md) · [Diseño]({base}/design.md) · [Tareas]({base}/tasks.md) · "
             f"{spec.verified}/{len(spec.criteria)} criterios verificados ({pct(spec.verified, len(spec.criteria))})"
             f" · {spec.state} · tareas {spec.done}/{spec.total}")
    lines = [f"## {spec.name}", "", links, ""]
    if not spec.criteria:
        return lines + ["Sin criterios de aceptación en requirements.md.", ""]
    lines += ["| Requisito | Criterio | Componentes | Decisiones | Tareas | Pruebas | Estado |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    previous = ""
    for crit in spec.criteria.values():
        title = spec.titles.get(crit.req, "")
        req = crit.req if crit.req == previous else f"**{crit.req}**" + (f" · {cell(title)}" if title else "")
        previous = crit.req
        lines.append(f"| {req} | {crit.cid} | {cell('; '.join(crit.components))} | {cell('; '.join(crit.decisions))}"
                     f" | {task_cell(crit.tasks)} | {evidence_cell(crit)} | {crit.state} |")
    return lines + [""]


def orphan_lines(orphans: list[Orphan]) -> list[str]:
    intro = ("Etiquetas y verificaciones manuales que no apuntan a un criterio existente. Siempre bloquean: "
             "corrige la etiqueta o el criterio.")
    lines = ["## Pruebas huérfanas", "", intro, ""]
    if not orphans:
        return lines + ["Ninguna.", ""]
    lines += ["| Ubicación | Etiqueta | Problema |", "| --- | --- | --- |"]
    for orphan in sorted(orphans, key=lambda o: (o.where, o.tag)):
        lines.append(f"| `{orphan.where}` | `{cell(orphan.tag)}` | {cell(orphan.problem)} |")
    return lines + [""]


def render(project: Project) -> str:
    note = ("> Generado por `kspec trace` (`.kiro/tools/kiro_trace.py generate`) a partir de las specs y de las "
            "etiquetas de las pruebas. No lo edites a mano: CI falla si no coincide con lo generado.")
    lines = ["# Matriz de trazabilidad", "", note, "", LEGEND, ""]
    if not project.specs:
        lines += ["No hay specs con requirements.md en .kiro/specs/.", ""]
    else:
        lines += summary_lines(project)
        for spec in project.specs:
            lines += spec_lines(spec)
    lines += orphan_lines(project.orphans)
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------ comprobaciones
def coverage_findings(project: Project) -> list[Finding]:
    findings = [Finding("ERROR", o.where, f"etiqueta «{o.tag}»: {o.problem}") for o in project.orphans]
    for spec in project.specs:
        missing = [c.cid for c in spec.criteria.values() if not c.verified]
        if missing and spec.closed:
            findings.append(Finding("ERROR", spec.name, f"spec cerrada con {len(missing)} criterio(s) sin prueba "
                                    f"etiquetada ni verificación manual: {', '.join(missing)}"))
        elif missing:
            shown = ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
            findings.append(Finding("AVISO", spec.name, f"{len(missing)} criterio(s) aún sin prueba "
                                    f"(bloquea al cerrar la spec): {shown}"))
    return project.findings + findings


def matrix_state(project: Project) -> Finding | None:
    path = project.root / MATRIX
    if not path.exists():
        if not project.specs:
            return None
        return Finding("ERROR", MATRIX.as_posix(), "no existe: genérala con kspec trace")
    if read(path).replace("\r\n", "\n") != render(project):
        return Finding("ERROR", MATRIX.as_posix(), "desactualizada: regenérala con kspec trace y commitéala")
    return None


def check(root: Path) -> list[Finding]:
    project = collect(root)
    stale = matrix_state(project)
    return coverage_findings(project) + ([stale] if stale else [])


def generate(root: Path) -> tuple[Project, list[Finding]]:
    project = collect(root)
    path = root / MATRIX
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(project), encoding="utf-8")
    return project, coverage_findings(project)


def totals(project: Project) -> str:
    total = sum(len(s.criteria) for s in project.specs)
    verified = sum(s.verified for s in project.specs)
    return f"{verified}/{total} criterios verificados ({pct(verified, total)})"


def summary(root: Path) -> str:
    """Estado en una línea para la sesión y kspec status."""
    project = collect(root)
    if not project.specs:
        return "sin specs con requisitos"
    parts = [totals(project)]
    if project.orphans:
        parts.append(f"{len(project.orphans)} prueba(s) huérfana(s)")
    stale = matrix_state(project)
    parts.append(f"matriz {stale.message}" if stale else "matriz al día")
    return " · ".join(parts)


# ------------------------------------------------------------------ commits (vista no commiteada)
def commit_index(root: Path, specs: list[Spec]) -> dict[tuple[str, str], list[str]]:
    """Commits por (spec, tarea) según sus trailers `Refs: <spec>#<tarea>`, del más reciente al más antiguo."""
    try:
        out = subprocess.run(["git", "log", f"--format={LOG_FORMAT}"], cwd=root, capture_output=True, text=True,
                             timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    index: dict[tuple[str, str], list[str]] = {}
    for record in out.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) < 3:
            continue
        for ref in (r.strip() for value in fields[2:] for r in value.split(",")):
            match = TRAILER_REF.match(ref)
            spec = find_spec(match.group(1), specs) if match else None
            if match and isinstance(spec, Spec):
                index.setdefault((spec.name, match.group(2)), []).append(f"{fields[0]} {fields[1]}")
    return index


def commits_view(project: Project, only: str = "") -> str:
    index = commit_index(project.root, project.specs)
    lines = ["## Commits por criterio", "",
             "Commits enlazados con el trailer `Refs: <spec>#<tarea>`, del más reciente al más antiguo.", ""]
    for spec in project.specs:
        if only and not (spec.name == only or spec.name.startswith(only + "-")):
            continue
        lines += [f"### {spec.name}", "", "| Criterio | Tareas | Commits | Estado |", "| --- | --- | --- | --- |"]
        for crit in spec.criteria.values():
            commits = dict.fromkeys(c for t in crit.tasks for c in index.get((spec.name, t.tid), []))
            shown = "<br>".join(f"`{cell(c)}`" for c in commits) or "—"
            lines.append(f"| {crit.cid} | {task_cell(crit.tasks)} | {shown} | {crit.state} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] == "commits":
        rest = list(argv[1:])
        only = rest.pop(rest.index("--spec") + 1) if "--spec" in rest and rest.index("--spec") + 1 < len(rest) else ""
        rest = [a for a in rest if a != "--spec"]
        print(commits_view(collect(Path(rest[0]) if rest else Path.cwd()), only), end="")
        return 0
    if not argv or argv[0] not in ("generate", "check") or len(argv) > 2:
        print(__doc__)
        return 2
    root = Path(argv[1]) if len(argv) == 2 else Path.cwd()
    if argv[0] == "generate":
        project, findings = generate(root)
        print(f"Generado: {MATRIX.as_posix()} ({totals(project)})")
    else:
        findings = check(root)
    for finding in findings:
        print(finding)
    if argv[0] == "check" and not any(f.level == "ERROR" for f in findings):
        print(f"OK: {MATRIX.as_posix()} al día, sin pruebas huérfanas")
    return 1 if any(f.level == "ERROR" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
