#!/usr/bin/env python3
"""Diagramas de arquitectura como código para el flujo estilo Kiro (draw.io + SVG, o Mermaid).

El modelo de un proyecto vive en docs/architecture/diagrams.py, importa este módulo y genera
docs/architecture/<archivo>.drawio y README.md. Solo usa la biblioteca estándar: se copia al
proyecto (.kiro/tools/kiro_diagrams.py) para que el modelo y la comprobación de CI no dependan del kit.

Uso:
  python3 kiro_diagrams.py check  [carpeta]          valida modelo, geometría y SVG (sin draw.io)
  python3 kiro_diagrams.py export [carpeta]          exporta cada página a svg/ (necesita draw.io)
  python3 kiro_diagrams.py render [carpeta] [n ...] [--out dir]  renderiza páginas a PNG para revisión visual
Salida: 0 sin errores, 1 con errores, 2 por uso incorrecto. La carpeta por defecto es docs/architecture.
"""
from __future__ import annotations

import fnmatch
import hashlib
import html
import itertools
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path("docs/architecture")
MODEL_FILE = "diagrams.py"
TEMPLATE_MARK = "KIRO-PLANTILLA"
HASH_MARK = "kiro-page-sha256:"
MERMAID_TYPES = ("C4Context", "C4Container", "C4Component", "C4Deployment", "C4Dynamic", "flowchart", "graph",
                 "sequenceDiagram", "erDiagram", "stateDiagram-v2", "stateDiagram", "classDiagram",
                 "architecture-beta", "block-beta")

# ------------------------------------------------------------------ estilos
FONT = "fontFamily=Helvetica;"
LEAF, CONTAINER, TEXT_ROLE, DECOR = "leaf", "container", "text", "decor"

PERSON = FONT + ("shape=mxgraph.c4.person2;whiteSpace=wrap;html=1;align=center;metaEdit=1;"
                 "points=[[0.5,0,0],[1,0.5,0],[1,0.75,0],[0.75,1,0],[0.5,1,0],[0.25,1,0],[0,0.75,0],[0,0.5,0]];"
                 "resizable=0;fillColor=#08427B;strokeColor=#073B6F;fontColor=#FFFFFF;fontSize=11;")
PERSON_EXT = PERSON.replace("#08427B", "#6B6477").replace("#073B6F", "#4D4D4D")
SYSTEM = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=5;fillColor=#1168BD;strokeColor=#0B4884;fontColor=#FFFFFF;fontSize=11;"
EXTERNAL = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=5;fillColor=#8C8496;strokeColor=#736782;fontColor=#FFFFFF;fontSize=11;"
FUTURE = FONT + ("rounded=1;whiteSpace=wrap;html=1;arcSize=5;fillColor=#F2F2F2;strokeColor=#999999;dashed=1;"
                 "dashPattern=6 4;fontColor=#666666;fontSize=11;")
CONTAINER_BOX = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=5;fillColor=#438DD5;strokeColor=#3C7FC0;fontColor=#FFFFFF;fontSize=11;"
DATABASE = FONT + ("shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#438DD5;"
                   "strokeColor=#3C7FC0;fontColor=#FFFFFF;fontSize=11;")
COMPONENT = FONT + ("rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#85BBF0;strokeColor=#5D82A8;fontColor=#0B2545;"
                    "fontSize=10;align=left;spacingLeft=8;spacingRight=6;verticalAlign=top;spacingTop=4;")
DEVICE = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=5;fillColor=#999999;strokeColor=#6E6E6E;fontColor=#FFFFFF;fontSize=11;"
BOUNDARY = FONT + ("rounded=1;whiteSpace=wrap;html=1;arcSize=1;fillColor=none;strokeColor=#5A6B7B;dashed=1;dashPattern=8 4;"
                   "fontColor=#2B3A4A;fontSize=12;fontStyle=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;")
BOUNDARY_LOCAL = BOUNDARY.replace("#5A6B7B", "#7A7A7A")
TRUST_BOUNDARY = BOUNDARY.replace("strokeColor=#5A6B7B;", "strokeColor=#C0392B;").replace("fontColor=#2B3A4A;", "fontColor=#C0392B;")
BAND = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=3;fontSize=12;fontStyle=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;"
NOTE = FONT + ("shape=note;whiteSpace=wrap;html=1;size=12;fillColor=#FFF8DC;strokeColor=#D6B656;fontSize=10;fontColor=#3A3A3A;"
               "align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;spacingRight=6;")
WARN = FONT + ("shape=note;whiteSpace=wrap;html=1;size=12;fillColor=#FDECEA;strokeColor=#C0392B;fontSize=10;fontColor=#7B241C;"
               "align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;spacingRight=6;")
PANEL = FONT + ("rounded=1;whiteSpace=wrap;html=1;arcSize=3;fillColor=#FFFFFF;strokeColor=#C8CDD3;fontSize=10;fontColor=#2B3A4A;"
                "align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;spacingRight=8;")
TEXT = FONT + "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=10;fontColor=#2B3A4A;"
STEP = FONT + ("rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#EEF4FB;strokeColor=#7FA7D1;fontSize=10;fontColor=#1B2A3A;"
               "align=left;spacingLeft=6;spacingRight=6;")
STAGE = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=10;fillColor=#E8F1FB;strokeColor=#3C7FC0;fontSize=10;fontColor=#0B2545;"
STAGE_OK = STAGE.replace("#E8F1FB", "#E6F4EA").replace("#3C7FC0", "#2E7D32")
STAGE_BAD = STAGE.replace("#E8F1FB", "#FDECEA").replace("#3C7FC0", "#C0392B")
DIAMOND = FONT + "rhombus;whiteSpace=wrap;html=1;fillColor=#FFF8DC;strokeColor=#D6B656;fontSize=10;fontColor=#3A3A3A;"
LANE = FONT + ("swimlane;horizontal=0;whiteSpace=wrap;html=1;startSize=34;fillColor=#F4F6F8;strokeColor=#C8CDD3;fontSize=12;"
               "fontStyle=1;fontColor=#2B3A4A;swimlaneFillColor=#FBFCFD;collapsible=0;")
# Flujo de datos (DFD) y estados
PROCESS = FONT + "ellipse;whiteSpace=wrap;html=1;fillColor=#438DD5;strokeColor=#3C7FC0;fontColor=#FFFFFF;fontSize=10;"
DATA_STORE = FONT + ("shape=partialRectangle;whiteSpace=wrap;html=1;left=0;right=0;fillColor=#EEF4FB;strokeColor=#3C7FC0;"
                     "fontColor=#0B2545;fontSize=10;")
STATE = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=30;fillColor=#E8F1FB;strokeColor=#3C7FC0;fontColor=#0B2545;fontSize=11;"
STATE_START = FONT + "ellipse;html=1;aspect=fixed;fillColor=#2B3A4A;strokeColor=#2B3A4A;"
STATE_END = FONT + "ellipse;html=1;shape=endState;aspect=fixed;fillColor=#2B3A4A;strokeColor=#2B3A4A;"
QUEUE = FONT + ("shape=mxgraph.flowchart.direct_data;whiteSpace=wrap;html=1;fillColor=#FDF2E3;strokeColor=#E0A040;"
                "fontColor=#5A3A00;fontSize=10;")
# Entidades del modelo conceptual
ENTITY_HEAD = FONT + ("rounded=0;whiteSpace=wrap;html=1;fillColor=#DCE9F7;strokeColor=#3C7FC0;strokeWidth=1.5;fontSize=11;"
                      "fontColor=#0B2545;align=center;verticalAlign=middle;")
ENTITY_BODY = FONT + ("rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#3C7FC0;strokeWidth=1.5;fontSize=10;"
                      "fontColor=#1B2A3A;align=left;verticalAlign=top;spacingLeft=8;spacingRight=8;spacingTop=8;")
# Tablas (rejilla de cajas: el comprobador geométrico también las valida)
TABLE_HEAD = FONT + ("rounded=0;whiteSpace=wrap;html=1;fillColor=#232F3E;strokeColor=#C8CDD3;fontColor=#FFFFFF;fontSize=10;"
                     "fontStyle=1;align=left;spacingLeft=8;spacingRight=6;verticalAlign=middle;")
TABLE_CELL = FONT + ("rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#C8CDD3;fontColor=#1B2A3A;fontSize=10;"
                     "align=left;spacingLeft=8;spacingRight=6;verticalAlign=middle;")
TABLE_KEY = TABLE_CELL.replace("fillColor=#FFFFFF;", "fillColor=#EEF4FB;")
# Aristas
EDGE = FONT + ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=blockThin;endFill=1;strokeColor=#6B7785;"
               "strokeWidth=1.3;fontSize=10;fontColor=#2B3A4A;labelBackgroundColor=#FFFFFF;")
EDGE_FUTURE = EDGE + "dashed=1;dashPattern=6 4;strokeColor=#9A9A9A;fontColor=#777777;"
EDGE_DASH = EDGE + "dashed=1;dashPattern=4 3;"
EDGE_BAD = EDGE + "dashed=1;dashPattern=4 3;strokeColor=#C0392B;fontColor=#C0392B;endArrow=cross;endFill=0;"
EDGE_STRAIGHT = EDGE.replace("edgeStyle=orthogonalEdgeStyle;", "")
ASSOC = FONT + ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;strokeColor=#3C7FC0;strokeWidth=1.3;"
                "fontSize=10;fontColor=#1B2A3A;labelBackgroundColor=#FFFFFF;")
# Secuencias
LIFE_HEAD = FONT + "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#438DD5;strokeColor=#3C7FC0;fontColor=#FFFFFF;fontSize=11;fontStyle=1;"
LIFE_HEAD_PERSON = LIFE_HEAD.replace("#438DD5", "#08427B").replace("#3C7FC0", "#073B6F")
LIFE_HEAD_EXT = LIFE_HEAD.replace("#438DD5", "#8C8496").replace("#3C7FC0", "#736782")
LIFE_LINE = FONT + "html=1;endArrow=none;dashed=1;dashPattern=4 4;strokeColor=#9AA5B1;strokeWidth=1;kiroRole=lifeline;"
MSG = FONT + ("html=1;endArrow=block;endFill=1;strokeColor=#2B3A4A;strokeWidth=1.2;fontSize=10;fontColor=#1B2A3A;"
              "verticalAlign=bottom;labelBackgroundColor=#FFFFFF;")
RET = MSG + "dashed=1;dashPattern=5 3;endArrow=open;endFill=0;strokeColor=#5A6B7B;fontColor=#3A4A5A;"
FRAME = FONT + ("shape=umlFrame;whiteSpace=wrap;html=1;width=210;height=22;boundedLbl=1;verticalAlign=middle;align=left;"
                "spacingLeft=6;fillColor=none;strokeColor=#5A6B7B;fontSize=10;fontStyle=1;fontColor=#2B3A4A;")
SEP = FONT + "html=1;endArrow=none;dashed=1;dashPattern=6 3;strokeColor=#5A6B7B;"
# Zonas de AWS
AZ = FONT + "fillColor=none;strokeColor=#147EBA;dashed=1;verticalAlign=top;fontStyle=1;fontColor=#147EBA;whiteSpace=wrap;html=1;fontSize=11;spacingTop=4;"
SECURITY_GROUP = FONT + ("fillColor=none;strokeColor=#DD3522;verticalAlign=top;fontStyle=0;fontColor=#DD3522;whiteSpace=wrap;html=1;"
                         "fontSize=10;align=left;spacingLeft=6;dashed=1;dashPattern=3 3;")
RIGHT_LABEL = "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=6;"

AWS_POINTS = ("points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],"
              "[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];")
# Color de cada categoría de iconos de AWS (paleta oficial de la biblioteca aws4)
AWS_COLORS = {"compute": "#ED7100", "database": "#C925D1", "storage": "#7AA116", "network": "#8C4FFF",
              "security": "#DD344C", "integration": "#E7157B", "management": "#E7157B", "cost": "#7AA116"}


def aws_resource(icon: str, category: str) -> str:
    """Icono de servicio de AWS (resIcon de la biblioteca aws4), p. ej. aws_resource("lambda", "compute")."""
    return (FONT + "sketch=0;" + AWS_POINTS + "outlineConnect=0;fontColor=#232F3E;fillColor=" + AWS_COLORS[category] +
            ";strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
            "fontSize=10;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4." + icon + ";")


def aws_icon(shape: str, category: str) -> str:
    """Icono de recurso de AWS (forma propia de aws4), p. ej. aws_icon("lambda_function", "compute")."""
    return (FONT + "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=" + AWS_COLORS[category] +
            ";strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
            "fontSize=10;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4." + shape + ";")


def aws_group(gr_icon: str, stroke: str, fill: str = "none", dashed: bool = False, font_color: str | None = None) -> str:
    """Grupo de AWS: group_aws_cloud_alt, group_region, group_vpc2, group_private_subnet…"""
    return (FONT + "outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=1;container=0;"
            "pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4." + gr_icon +
            f";strokeColor={stroke};fillColor={fill};verticalAlign=top;align=left;spacingLeft=30;"
            f"fontColor={font_color or stroke};dashed={int(dashed)};")


def label(name: str, kind: str | None = None, desc: str | None = None) -> str:
    """Etiqueta C4: nombre en negrita, [tipo · tecnología] y descripción."""
    text = f"<b>{name}</b>"
    if kind:
        text += f"<br><span style=\"font-size:9px\">[{kind}]</span>"
    if desc:
        text += f"<br><br><span style=\"font-size:10px\">{desc}</span>"
    return text


def plain(style: str) -> str:
    """Versión recta de un estilo de arista, para las muestras de la leyenda."""
    return style.replace("edgeStyle=orthogonalEdgeStyle;", "")


C4_LEGEND = [
    (PERSON.replace("shape=mxgraph.c4.person2;", "rounded=1;"), "Persona", "box"),
    (SYSTEM, "Sistema / contenedor propio", "box"),
    (EXTERNAL, "Sistema externo", "box"),
    (DEVICE, "Dispositivo físico", "box"),
    (FUTURE, "Propuesto o fase futura", "box"),
    (BOUNDARY, "Límite (sistema o equipo)", "box"),
    (EDGE_STRAIGHT, "Relación [tecnología]", "line"),
    (plain(EDGE_FUTURE), "Relación propuesta o futura", "line"),
]


# ------------------------------------------------------------------ modelo
@dataclass
class Cell:
    kind: str  # "v" (vértice), "e" (arista entre celdas) o "l" (línea libre)
    cid: str
    value: str
    style: str
    data: tuple[Any, ...]


@dataclass
class Page:
    num: int
    slug: str
    title: str
    question: str
    subtitle: str
    w: int = 1920
    h: int = 1200
    cells: list[Cell] = field(default_factory=list)
    footer: str = ""
    version: str = ""
    project: str = ""
    total: int = 0

    @property
    def pid(self) -> str:
        return self.slug

    def _id(self, cid: str) -> str:
        return f"{self.slug}-{cid}"

    def v(self, cid: str, value: str, style: str, x: float, y: float, w: float, h: float, role: str = LEAF) -> str:
        """Vértice. role: leaf (no debe solaparse), container (contiene a otros), text o decor."""
        self.cells.append(Cell("v", self._id(cid), value, style + f"kiroRole={role};", (x, y, w, h)))
        return self._id(cid)

    def box(self, cid: str, value: str, style: str, x: float, y: float, w: float, h: float) -> str:
        return self.v(cid, value, style, x, y, w, h, LEAF)

    def group(self, cid: str, value: str, style: str, x: float, y: float, w: float, h: float) -> str:
        return self.v(cid, value, style, x, y, w, h, CONTAINER)

    def text(self, cid: str, value: str, x: float, y: float, w: float, h: float, style: str = TEXT) -> str:
        return self.v(cid, value, style, x, y, w, h, TEXT_ROLE)

    def e(self, cid: str, src: str, tgt: str, value: str = "", style: str = EDGE,
          pts: list[tuple[float, float]] | None = None, exit: tuple[float, float] | None = None,
          entry: tuple[float, float] | None = None, lx: float | None = None) -> None:
        """Arista entre dos celdas de la página. exit/entry: punto relativo (0-1); lx: posición de la etiqueta (-1 a 1)."""
        st = style
        if exit:
            st += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry:
            st += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        self.cells.append(Cell("e", self._id(cid), value, st, (self._id(src), self._id(tgt), pts or [], lx)))

    def line(self, cid: str, p1: tuple[float, float], p2: tuple[float, float], value: str = "", style: str = MSG,
             pts: list[tuple[float, float]] | None = None) -> None:
        """Línea entre dos puntos (mensajes de secuencia, separadores, muestras de leyenda)."""
        self.cells.append(Cell("l", self._id(cid), value, style, (p1, p2, pts or [])))

    # ---------------------------------------------------------- piezas comunes
    def header(self) -> None:
        dark = FONT + "rounded=0;whiteSpace=wrap;html=1;fillColor=#232F3E;strokeColor=none;"
        txt = FONT + "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;"
        self.v("hdr", "", dark, 0, 0, self.w, 78, DECOR)
        self.v("hdr-t", f"<b>{self.title}</b>", txt + "align=left;verticalAlign=middle;fontSize=22;fontColor=#FFFFFF;",
               30, 8, self.w - 360, 36, DECOR)
        self.v("hdr-s", self.subtitle, txt + "align=left;verticalAlign=middle;fontSize=12;fontColor=#C9D3DD;",
               30, 42, self.w - 360, 28, DECOR)
        self.v("hdr-n", f"<b>{self.num} / {self.total}</b><br><span style=\"font-size:10px\">{self.project} · v{self.version}</span>",
               txt + "align=right;verticalAlign=middle;fontSize=14;fontColor=#FFFFFF;", self.w - 320, 14, 290, 50, DECOR)
        if self.footer:
            self.v("ftr", self.footer, txt + "align=left;verticalAlign=middle;fontSize=10;fontColor=#7A8794;",
                   30, self.h - 34, self.w - 60, 24, DECOR)

    def legend(self, x: float, y: float, items: list[tuple[str, str, str]], w: float = 250) -> None:
        """Leyenda: items = [(estilo, texto, "box" | "line")]."""
        h = 34 + 26 * len(items)
        self.v("lg", "<b>Leyenda</b>", PANEL, x, y, w, h, CONTAINER)
        for i, (style, text, kind) in enumerate(items):
            yy = y + 30 + 26 * i
            if kind == "box":
                self.v(f"lg{i}b", "", style, x + 12, yy + 2, 34, 18)
            else:
                self.line(f"lg{i}l", (x + 12, yy + 11), (x + 46, yy + 11), "", style)
            self.v(f"lg{i}t", text, TEXT + "verticalAlign=middle;", x + 54, yy, w - 62, 22, TEXT_ROLE)

    def table(self, cid: str, x: float, y: float, widths: list[float], header: list[str], rows: list[list[str]],
              row_h: float | list[float] = 60, head_h: float = 32) -> float:
        """Tabla como rejilla de cajas contiguas: cabecera, primera columna destacada y celdas. Devuelve la y final."""
        heights = row_h if isinstance(row_h, list) else [row_h] * len(rows)
        if len(header) != len(widths) or any(len(r) != len(widths) for r in rows) or len(heights) != len(rows):
            raise ValueError(f"tabla '{cid}': cabecera, filas, anchos y altos no cuadran")
        cx = x
        for j, (w, text) in enumerate(zip(widths, header, strict=True)):
            self.box(f"{cid}-h{j}", text, TABLE_HEAD, cx, y, w, head_h)
            cx += w
        yy = y + head_h
        for i, (row, h) in enumerate(zip(rows, heights, strict=True)):
            cx = x
            for j, (w, text) in enumerate(zip(widths, row, strict=True)):
                self.box(f"{cid}-{i}-{j}", text, TABLE_KEY if j == 0 else TABLE_CELL, cx, yy, w, h)
                cx += w
            yy += h
        return yy

    def entity(self, cid: str, title: str, subtitle: str, items: list[str], rule: str,
               x: float, y: float, w: float) -> tuple[float, float, float, float]:
        """Entidad conceptual (cabecera + cuerpo). Devuelve (x, y, w, h) del conjunto; la cabecera es '<cid>-h'."""
        body = "<br>".join(f"• {it}" for it in items) + (f"<br><br><i>{rule}</i>" if rule else "")
        chars = max(10, int(w / 6.2))
        lines = len(items) + (2 + math.ceil(len(rule) / chars) if rule else 0)
        h = 24 + 15 * lines
        self.box(cid + "-h", f"<b>{title}</b><br><span style=\"font-size:9px\">{subtitle}</span>", ENTITY_HEAD, x, y, w, 40)
        self.box(cid, body, ENTITY_BODY, x, y + 40, w, h)
        return x, y, w, 40 + h

    def sequence(self, actors: list[tuple[str, str, str]], steps: list[tuple[Any, ...]],
                 x0: float = 120, gap: float = 200, top: float = 110) -> float:
        """Diagrama de secuencia. actors = [(id, nombre, "" | "p" persona | "x" externo)].

        steps: ("m", a, b, texto) mensaje · ("r", a, b, texto) respuesta · ("self", a, texto, alto) acción interna ·
        ("frame", texto, a, b, ancho_etiqueta[, extra_derecha]) abre loop/alt/opt · ("sep",) separa ramas de alt ·
        ("end",) cierra el marco · ("gap", px). Devuelve la y final.
        """
        xs: dict[str, float] = {}
        bottom = self.h - 60
        for i, (aid, name, kind) in enumerate(actors):
            x = x0 + i * gap
            xs[aid] = x
            st = {"p": LIFE_HEAD_PERSON, "x": LIFE_HEAD_EXT}.get(kind, LIFE_HEAD)
            self.box(f"h-{aid}", name, st, x - 85, top, 170, 50)
            self.line(f"ll-{aid}", (x, top + 50), (x, bottom), "", LIFE_LINE)
        y = top + 92
        stack: list[tuple[int, float, float, float]] = []
        for k, s in enumerate(steps, start=1):
            t = s[0]
            if t in ("m", "r"):
                _, a, b, text = s
                self.line(f"m{k}", (xs[a], y), (xs[b], y), text, MSG if t == "m" else RET)
                y += 34
            elif t == "self":
                _, a, text, hh = s
                self.box(f"s{k}", text, STEP, xs[a] + 10, y - 12, 310, hh)
                y += hh + 12
            elif t == "frame":
                _, text, a, b, label_w = s[:5]
                right = s[5] if len(s) > 5 else 0
                x = xs[a] - 100 + 8 * len(stack)
                w = xs[b] - xs[a] + 200 + right - 16 * len(stack)
                self.cells.append(Cell("v", self._id(f"f{k}"), text,
                                       FRAME.replace("width=210", f"width={label_w}") + f"kiroRole={CONTAINER};",
                                       (x, y - 12, w, 0)))
                stack.append((len(self.cells) - 1, y - 12, x, w))
                y += 34
            elif t == "sep":
                _, y0, x, w = stack[-1]
                self.line(f"sp{k}", (x, y - 6), (x + w, y - 6), "", SEP)
                y += 10
            elif t == "end":
                idx, y0, x, w = stack.pop()
                cell = self.cells[idx]
                cell.data = (x, y0, w, y - y0 - 4)
                y += 12
            elif t == "gap":
                y += s[1]
            else:
                raise ValueError(f"paso de secuencia desconocido: {t!r}")
        if stack:
            raise ValueError("marco de secuencia sin cerrar: falta ('end',)")
        return y


@dataclass
class Diagram:
    """Documento con varias páginas. Una página por vista del catálogo de la skill architecture-diagrams."""
    project: str
    version: str
    sources: str = ".kiro/steering y docs/adr"
    filename: str = "arquitectura.drawio"
    pages: list[Page] = field(default_factory=list)

    def page(self, slug: str, title: str, question: str, subtitle: str, w: int = 1920, h: int = 1200) -> Page:
        if any(p.slug == slug for p in self.pages):
            raise ValueError(f"slug de página repetido: {slug}")
        p = Page(len(self.pages) + 1, slug, title, question, subtitle, w, h,
                 footer=f"Fuente: <b>{self.sources}</b> · Propuesto y fases futuras en gris discontinuo",
                 version=self.version, project=self.project)
        self.pages.append(p)
        return p

    def to_xml(self) -> str:
        for p in self.pages:
            p.total = len(self.pages)
            if not any(c.cid == p._id("hdr") for c in p.cells):
                p.header()
        mxfile = ET.Element("mxfile", {"host": "kiro-diagrams", "compressed": "false"})
        for p in self.pages:
            d = ET.SubElement(mxfile, "diagram", {"id": p.slug, "name": f"{p.num} · {p.title}"})
            model = ET.SubElement(d, "mxGraphModel", {
                "dx": "1400", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1", "tooltips": "1",
                "connect": "1", "arrows": "1", "fold": "1", "page": "1", "pageScale": "1", "pageWidth": str(p.w),
                "pageHeight": str(p.h), "math": "0", "shadow": "0", "background": "#FFFFFF"})
            root = ET.SubElement(model, "root")
            ET.SubElement(root, "mxCell", {"id": f"{p.slug}-0"})
            ET.SubElement(root, "mxCell", {"id": f"{p.slug}-1", "parent": f"{p.slug}-0"})
            for c in p.cells:
                _cell_xml(root, p.slug, c)
        ET.indent(mxfile, space="  ")
        return ET.tostring(mxfile, encoding="unicode") + "\n"

    def readme(self, folder: Path | None = None) -> str:
        """README índice: vistas, ADR de docs/adr y enlaces al steering (folder = carpeta del modelo)."""
        rows = "\n".join(f"| {p.num} · {p.title} | {p.question} | [{svg_name(p.num, p.slug)}](svg/{svg_name(p.num, p.slug)}) |"
                         for p in self.pages)
        return README_TEMPLATE.format(project=self.project, filename=self.filename, rows=rows,
                                      related=related_docs(folder) if folder else "")

    def main(self, folder: Path, argv: list[str] | None = None) -> int:
        """Escribe el .drawio y README.md en folder (o en --emit <carpeta>)."""
        args = sys.argv[1:] if argv is None else argv
        out = Path(args[args.index("--emit") + 1]) if "--emit" in args else folder
        out.mkdir(parents=True, exist_ok=True)
        (out / self.filename).write_text(self.to_xml(), encoding="utf-8")
        (out / "README.md").write_text(self.readme(folder), encoding="utf-8")
        print(f"Generado: {out / self.filename} ({len(self.pages)} páginas) y README.md")
        return 0


def _cell_xml(root: ET.Element, slug: str, c: Cell) -> None:
    attrs = {"id": c.cid, "value": c.value, "style": c.style, "parent": f"{slug}-1"}
    if c.kind == "v":
        attrs["vertex"] = "1"
        el = ET.SubElement(root, "mxCell", attrs)
        x, y, w, h = c.data
        ET.SubElement(el, "mxGeometry", {"x": _n(x), "y": _n(y), "width": _n(w), "height": _n(h), "as": "geometry"})
        return
    attrs["edge"] = "1"
    if c.kind == "e":
        src, tgt, pts, lx = c.data
        attrs.update(source=src, target=tgt)
        el = ET.SubElement(root, "mxCell", attrs)
        geo = ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
        if lx is not None:
            geo.set("x", _n(lx))
    else:
        p1, p2, pts = c.data
        el = ET.SubElement(root, "mxCell", attrs)
        geo = ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
        ET.SubElement(geo, "mxPoint", {"x": _n(p1[0]), "y": _n(p1[1]), "as": "sourcePoint"})
        ET.SubElement(geo, "mxPoint", {"x": _n(p2[0]), "y": _n(p2[1]), "as": "targetPoint"})
    if pts:
        arr = ET.SubElement(geo, "Array", {"as": "points"})
        for px, py in pts:
            ET.SubElement(arr, "mxPoint", {"x": _n(px), "y": _n(py)})


def _n(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}".rstrip("0")


def svg_name(num: int, slug: str) -> str:
    return f"{num:02d}-{slug}.svg"


README_TEMPLATE = """# Diagramas de arquitectura · {project}

> Generado por `docs/architecture/diagrams.py`. No edites este archivo ni el `.drawio` a mano: cambia el modelo y regenera.

| Vista | Pregunta que responde | Imagen |
| --- | --- | --- |
{rows}
{related}
## Regenerar

```bash
python3 docs/architecture/diagrams.py        # modelo -> {filename} y README.md
kspec diagrams export                        # {filename} -> svg/ (necesita draw.io Desktop)
kspec diagrams check                         # modelo, geometría y SVG al día (también en CI)
```

## Convenciones

- Colores C4: persona en azul oscuro, contenedor propio en azul, sistema externo en gris violeta y dispositivo en gris.
- Lo *Propuesto* y las fases futuras van en gris discontinuo; las decisiones abiertas, en notas rojas con su ID.
- Las vistas de infraestructura usan los iconos oficiales de AWS (biblioteca `aws4` de draw.io).
- Los nombres de clases de las vistas de componentes son orientativos: los fija cada spec.
- Si un cambio afecta a un componente o a un flujo, actualiza el modelo y regenera en el mismo PR.
"""


# ------------------------------------------------------------------ ADR y documentación relacionada
ADR_HEADING = re.compile(r"^#\s+(\d{4})\.?\s+(.+?)\s*$", re.MULTILINE)
ADR_STATUS = re.compile(r"\*\*Estado:\*\*\s*([^\n(]+)")
ADR_TEMPLATE_MARKS = ("<problema", "<qué se decide", "<alternativa>", "<por qué no>", "<qué se gana", "<documentación oficial",
                      "<IDs")
STEERING_FILES = ("product.md", "tech.md", "structure.md")


def slugify(title: str) -> str:
    """Título -> nombre de archivo en kebab-case, sin tildes ni símbolos."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:60] or "decision"


def adr_entries(adr_dir: Path) -> list[tuple[str, str, str, str]]:
    """[(número, título, estado, archivo)] de docs/adr/NNNN-*.md, en orden."""
    out = []
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")) if adr_dir.is_dir() else []:
        text = path.read_text(encoding="utf-8")
        head, status = ADR_HEADING.search(text), ADR_STATUS.search(text)
        out.append((path.name[:4], head.group(2) if head else path.stem[5:], status.group(1).strip() if status else "?", path.name))
    return out


def next_adr_number(adr_dir: Path) -> int:
    return max((int(n) for n, *_ in adr_entries(adr_dir)), default=0) + 1


def related_docs(folder: Path) -> str:
    """Secciones del README que enlazan los ADR y el steering: una sola fuente por dato."""
    adrs = adr_entries(folder.parent / "adr")
    lines = ["", "## Decisiones de arquitectura (ADR)", ""]
    if adrs:
        lines += ["| ADR | Decisión | Estado |", "| --- | --- | --- |"]
        lines += [f"| [{n}](../adr/{f}) | {t} | {s} |" for n, t, s, f in adrs]
    else:
        lines.append("Aún no hay ADR en `docs/adr/`. Crea uno con `kspec adr new \"<título>\"`.")
    steering = folder.parent.parent / ".kiro" / "steering"
    present = [f for f in STEERING_FILES if (steering / f).exists()]
    if present:
        lines += ["", "## Steering", "", "Contexto, decisiones abiertas y restricciones: "
                  + " · ".join(f"[{f}](../../.kiro/steering/{f})" for f in present) + "."]
    return "\n".join(lines) + "\n"


def check_adrs(folder: Path) -> list[Finding]:
    """Los ADR no conservan marcadores de la plantilla."""
    out = []
    for num, _, _, name in adr_entries(folder.parent / "adr"):
        text = (folder.parent / "adr" / name).read_text(encoding="utf-8")
        if any(mark in text for mark in ADR_TEMPLATE_MARKS):
            out.append(Finding("ERROR", f"ADR {num}", f"{name} conserva marcadores de la plantilla: complétalo"))
    return out


# ------------------------------------------------------------------ cobertura del catálogo
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".kiro", "__pycache__", ".terraform", ".next"}
NOT_APPLICABLE = ".no-aplica"
# slug de la vista: (patrones que la disparan, slugs aceptados, motivo)
TRIGGERS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "modelo-fisico": (("**/alembic/versions/*.py", "**/migrations/*.py", "**/migrations/*.sql", "**/prisma/schema.prisma",
                       "**/db/migrate/*.rb", "**/flyway/**/*.sql"), ("modelo-fisico", "erd"), "hay migraciones de base de datos"),
    "red-y-despliegue": (("**/*.tf", "**/cdk.json", "**/template.yaml", "**/template.yml", "**/serverless.yml",
                          "**/Pulumi.yaml", "**/*.bicep"), ("red-y-despliegue", "despliegue", "infraestructura"),
                         "hay infraestructura como código"),
    "ci-cd": ((".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
               ".circleci/config.yml"), ("ci-cd",), "hay un pipeline de CI/CD"),
}


def _project_files(root: Path) -> list[str]:
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        rel = Path(base).relative_to(root).as_posix()
        out += [f"{rel}/{f}" if rel != "." else f for f in files]
    return out


def detect_triggers(root: Path) -> dict[str, str]:
    """Vistas que el repositorio exige ya (migraciones, IaC, CI/CD) -> primer archivo que la dispara."""
    files = _project_files(root)
    found = {}
    for slug, (patterns, _, _) in TRIGGERS.items():
        hit = next((f for f in files for pat in patterns if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch("/" + f, pat)), None)
        if hit:
            found[slug] = hit
    return found


def present_slugs(folder: Path) -> set[str]:
    drawio = drawio_file(folder)
    if (folder / MODEL_FILE).exists() and drawio is not None:
        return {d.get("id", "") for d in ET.parse(drawio).getroot().findall("diagram")}
    return {re.sub(r"^\d+-", "", p.stem) for p in folder.glob("*.md") if p.name != "README.md"}


def not_applicable(folder: Path) -> dict[str, str]:
    """docs/architecture/.no-aplica: una línea «slug: motivo» por vista disparada que no aplica."""
    path = folder / NOT_APPLICABLE
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if line.strip() and not line.lstrip().startswith("#"):
            slug, _, reason = line.partition(":")
            out[slug.strip()] = reason.strip()
    return out


def check_coverage(folder: Path) -> list[Finding]:
    """Cada vista que el repositorio dispara existe o está justificada en .no-aplica."""
    root = folder.resolve().parents[1]
    present, exempt = present_slugs(folder), not_applicable(folder)
    out = []
    for slug, path in detect_triggers(root).items():
        aliases, reason = TRIGGERS[slug][1], TRIGGERS[slug][2]
        if any(s.startswith(a) for s in present for a in aliases):
            continue
        if slug in exempt:
            if not exempt[slug]:
                out.append(Finding("ERROR", NOT_APPLICABLE, f"«{slug}» no aplica, pero falta el motivo («{slug}: motivo»)"))
            continue
        out.append(Finding("ERROR", "cobertura", f"falta la vista «{slug}»: {reason} ({path}). Créala con /architecture-diagrams "
                           f"o justifícala en {NOT_APPLICABLE}"))
    return out


# ------------------------------------------------------------------ comprobaciones
@dataclass
class Finding:
    level: str  # "ERROR" o "AVISO"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}  {self.where}: {self.message}"


@dataclass
class Box:
    cid: str
    role: str
    x: float
    y: float
    w: float
    h: float
    value: str
    style: str

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def contains(self, o: Box, tol: float = 1) -> bool:
        return o.x >= self.x - tol and o.y >= self.y - tol and o.x2 <= self.x2 + tol and o.y2 <= self.y2 + tol

    def overlap(self, o: Box) -> float:
        dx = min(self.x2, o.x2) - max(self.x, o.x)
        dy = min(self.y2, o.y2) - max(self.y, o.y)
        return min(dx, dy) if dx > 0 and dy > 0 else 0.0


def style_map(style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in style.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
        elif part:
            out[part] = ""
    return out


def page_hash(diagram: ET.Element) -> str:
    """SHA-256 de la forma canónica (C14N) de una página: identifica el contenido que se exportó."""
    canonical = ET.canonicalize(ET.tostring(diagram, encoding="unicode"), strip_text=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _boxes(diagram: ET.Element) -> tuple[dict[str, Box], list[ET.Element]]:
    boxes: dict[str, Box] = {}
    edges: list[ET.Element] = []
    for c in diagram.iter("mxCell"):
        if c.get("edge") == "1":
            edges.append(c)
            continue
        g = c.find("mxGeometry")
        if c.get("vertex") != "1" or g is None:
            continue
        st = c.get("style") or ""
        role = style_map(st).get("kiroRole", LEAF)
        boxes[c.get("id", "")] = Box(c.get("id", ""), role, float(g.get("x", 0)), float(g.get("y", 0)),
                                     float(g.get("width", 0)), float(g.get("height", 0)), c.get("value") or "", st)
    return boxes, edges


def _visible_text(value: str) -> list[str]:
    text = re.sub(r"<br\s*/?>|<hr\s*/?>|</div>", "\n", value, flags=re.IGNORECASE)
    return [html.unescape(re.sub(r"<[^>]+>", "", line)).strip() for line in text.split("\n")]


def text_overflows(b: Box) -> bool:
    """Estimación conservadora: el texto del cuadro no cabe en su alto (con ajuste de línea)."""
    st = style_map(b.style)
    if "text" in st or b.role in (DECOR, TEXT_ROLE) or "verticalLabelPosition" in st or not b.value:
        return False
    size = float(st.get("fontSize", 11))
    usable = b.w - float(st.get("spacingLeft", 4)) - float(st.get("spacingRight", 4)) - 4
    if usable <= 0:
        return True
    lines = sum(max(1, math.ceil(len(line) * size * 0.48 / usable)) for line in _visible_text(b.value))
    need = lines * size * 1.2 + float(st.get("spacingTop", 0)) + 6
    return need > b.h + 6


def _anchor(b: Box, rel: tuple[float, float] | None) -> tuple[float, float]:
    if rel is None:
        return b.x + b.w / 2, b.y + b.h / 2
    return b.x + b.w * rel[0], b.y + b.h * rel[1]


def _rel(st: dict[str, str], prefix: str) -> tuple[float, float] | None:
    if f"{prefix}X" in st and f"{prefix}Y" in st:
        return float(st[f"{prefix}X"]), float(st[f"{prefix}Y"])
    return None


def _segment_hits(p: tuple[float, float], q: tuple[float, float], b: Box, pad: float = 3) -> bool:
    if p[0] == q[0]:
        lo, hi = sorted((p[1], q[1]))
        return b.x + pad < p[0] < b.x2 - pad and lo < b.y2 - pad and hi > b.y + pad
    if p[1] == q[1]:
        lo, hi = sorted((p[0], q[0]))
        return b.y + pad < p[1] < b.y2 - pad and lo < b.x2 - pad and hi > b.x + pad
    return False


def check_geometry(diagram: ET.Element) -> list[Finding]:
    """Solapes entre cajas, cajas que cruzan el borde de un contenedor, texto desbordado y aristas rotas."""
    name = diagram.get("name", "?")
    out: list[Finding] = []
    boxes, edges = _boxes(diagram)
    leaves = [b for b in boxes.values() if b.role == LEAF and b.w > 0 and b.h > 0]
    containers = [b for b in boxes.values() if b.role == CONTAINER]
    for i, a in enumerate(leaves):
        for b in leaves[i + 1:]:
            if a.overlap(b) > 2 and not a.contains(b) and not b.contains(a):
                out.append(Finding("ERROR", name, f"'{a.cid}' y '{b.cid}' se solapan"))
        for c in containers:
            if a.overlap(c) > 2 and not c.contains(a, tol=2) and not a.contains(c):
                out.append(Finding("AVISO", name, f"'{a.cid}' cruza el borde de '{c.cid}'"))
        if text_overflows(a):
            out.append(Finding("AVISO", name, f"el texto de '{a.cid}' puede no caber en su caja"))
    for e in edges:
        st = style_map(e.get("style") or "")
        if st.get("kiroRole") == "lifeline":  # en una secuencia, las cajas de acción van junto a las líneas de vida
            continue
        src, tgt = e.get("source"), e.get("target")
        geo = e.find("mxGeometry")
        arr = geo.find("Array") if geo is not None else None
        pts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in (arr if arr is not None else [])]
        if src or tgt:
            missing = [x for x in (src, tgt) if x not in boxes]
            if missing:
                out.append(Finding("ERROR", name, f"la arista '{e.get('id')}' apunta a celdas inexistentes: {missing}"))
                continue
            path = [_anchor(boxes[str(src)], _rel(st, "exit"))] + pts + [_anchor(boxes[str(tgt)], _rel(st, "entry"))]
            skip = {src, tgt}
        else:
            if geo is None:
                continue
            ends = {p.get("as"): (float(p.get("x", 0)), float(p.get("y", 0))) for p in geo.findall("mxPoint")}
            if "sourcePoint" not in ends or "targetPoint" not in ends:
                continue
            path = [ends["sourcePoint"]] + pts + [ends["targetPoint"]]
            skip = set()
        for p, q in itertools.pairwise(path):
            for b in leaves:
                if b.cid not in skip and _segment_hits(p, q, b):
                    out.append(Finding("AVISO", name, f"la arista '{e.get('id')}' atraviesa '{b.cid}'"))
    return out


def find_model_dir(folder: Path) -> str:
    if (folder / MODEL_FILE).exists():
        return "drawio"
    if any(_mermaid_blocks(p) for p in folder.glob("*.md") if p.name != "README.md"):
        return "mermaid"
    return ""


def drawio_file(folder: Path) -> Path | None:
    files = sorted(folder.glob("*.drawio"))
    return files[0] if files else None


def _mermaid_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```mermaid\n(.*?)```", text, flags=re.DOTALL)


def check_mermaid(folder: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in sorted(folder.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        if text.count("```") % 2:
            out.append(Finding("ERROR", path.name, "bloque de código sin cerrar"))
        blocks = _mermaid_blocks(path)
        if not blocks:
            out.append(Finding("ERROR", path.name, "no tiene ningún bloque ```mermaid"))
        for block in blocks:
            first = next((ln.strip() for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("%%")), "")
            if not first.startswith(MERMAID_TYPES):
                out.append(Finding("ERROR", path.name, f"tipo de diagrama Mermaid desconocido: {first[:40]!r}"))
    readme = folder / "README.md"
    if not readme.exists():
        out.append(Finding("ERROR", str(folder), "falta README.md con el índice de vistas y de ADR"))
    else:
        text = readme.read_text(encoding="utf-8")
        out += [Finding("ERROR", "README.md", f"no enlaza el ADR {name}") for *_, name in adr_entries(folder.parent / "adr")
                if name not in text]
    return out


def check_drawio(folder: Path, run_model: bool = True) -> list[Finding]:
    out: list[Finding] = []
    drawio = drawio_file(folder)
    if drawio is None:
        return [Finding("ERROR", str(folder), "no hay ningún .drawio: ejecuta python3 docs/architecture/diagrams.py")]
    model = folder / MODEL_FILE
    if model.exists() and TEMPLATE_MARK in model.read_text(encoding="utf-8"):
        out.append(Finding("ERROR", MODEL_FILE, "sigue siendo la plantilla: sustituye los ejemplos por el sistema real "
                           f"y borra la marca {TEMPLATE_MARK}"))
    if run_model and model.exists():
        out += _check_model_fresh(folder, drawio)
    try:
        root = ET.parse(drawio).getroot()
    except ET.ParseError as exc:
        return out + [Finding("ERROR", drawio.name, f"XML inválido: {exc}")]
    pages = root.findall("diagram")
    if not pages:
        out.append(Finding("ERROR", drawio.name, "no tiene páginas"))
    for num, d in enumerate(pages, start=1):
        out += check_geometry(d)
        svg = folder / "svg" / svg_name(num, d.get("id", f"pagina-{num}"))
        if not svg.exists():
            out.append(Finding("ERROR", d.get("name", "?"), f"falta {svg.relative_to(folder)}: ejecuta kspec diagrams export"))
            continue
        mark = re.search(HASH_MARK + r"([0-9a-f]{64})", svg.read_text(encoding="utf-8")[:2000])
        if not mark or mark.group(1) != page_hash(d):
            out.append(Finding("ERROR", d.get("name", "?"), f"{svg.name} no corresponde a la página actual: "
                               "ejecuta kspec diagrams export"))
    return out


def _check_model_fresh(folder: Path, drawio: Path) -> list[Finding]:
    with tempfile.TemporaryDirectory(prefix="kiro-diagrams-") as tmp:
        result = subprocess.run([sys.executable, str(folder / MODEL_FILE), "--emit", tmp], capture_output=True,
                                text=True, timeout=120, check=False)
        if result.returncode != 0:
            return [Finding("ERROR", MODEL_FILE, f"falla al ejecutarse: {(result.stderr or result.stdout).strip()[-300:]}")]
        out: list[Finding] = []
        fresh = Path(tmp) / drawio.name
        if not fresh.exists() or fresh.read_text(encoding="utf-8") != drawio.read_text(encoding="utf-8"):
            out.append(Finding("ERROR", drawio.name, "no coincide con el modelo: ejecuta python3 docs/architecture/diagrams.py"))
        readme = folder / "README.md"
        if not readme.exists() or (Path(tmp) / "README.md").read_text(encoding="utf-8") != readme.read_text(encoding="utf-8"):
            out.append(Finding("ERROR", "README.md", "no coincide con el modelo: ejecuta python3 docs/architecture/diagrams.py"))
        return out


def check(folder: Path, run_model: bool = True) -> list[Finding]:
    """Diagramas (modelo, geometría, SVG o Mermaid), cobertura del catálogo y ADR completos."""
    fmt = find_model_dir(folder) if folder.is_dir() else ""
    if fmt == "drawio":
        findings = check_drawio(folder, run_model)
    elif fmt == "mermaid":
        findings = check_mermaid(folder)
    else:
        return [Finding("ERROR", str(folder), "no hay diagramas: falta diagrams.py (draw.io) o vistas .md con Mermaid")]
    return findings + check_coverage(folder) + check_adrs(folder)


def summary(folder: Path) -> str:
    """Estado en una línea para la sesión y kspec status (rápido: no ejecuta el modelo)."""
    fmt = find_model_dir(folder) if folder.is_dir() else ""
    if not fmt:
        return "sin diagramas en docs/architecture: ejecuta /architecture-diagrams"
    errors = sum(f.level == "ERROR" for f in check(folder, run_model=False))
    views, adrs = len(present_slugs(folder)), len(adr_entries(folder.parent / "adr"))
    state = "sin problemas" if not errors else f"{errors} problema(s): kspec diagrams check"
    return f"{views} vistas ({fmt}) · {adrs} ADR · {state}"


# ------------------------------------------------------------------ exportación con draw.io
def drawio_command() -> list[str] | None:
    """Comando de la CLI de draw.io Desktop. En Linux necesita la sesión X11 (sin ella, Electron falla).
    DRAWIO_BIN fija la ruta; DRAWIO_BIN=none lo desactiva (fuerza Mermaid y no exporta)."""
    if os.environ.get("DRAWIO_BIN", "").lower() == "none":
        return None
    exe = os.environ.get("DRAWIO_BIN") or shutil.which("drawio") or shutil.which("draw.io")
    mac = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")
    if exe is None and mac.exists():
        exe = str(mac)
    if exe is None:
        return None
    cmd = [exe]
    if platform.system() == "Linux":
        cmd += ["--no-sandbox", "--disable-gpu", "--ozone-platform=x11"]
    return cmd


def clean_svg(svg: str, digest: str) -> str:
    """Quita los PNG de respaldo de cada etiqueta (multiplican el tamaño ~25 veces), fija el fondo blanco
    (el texto oscuro no se lee en visores con tema oscuro) y anota el hash de la página exportada."""
    svg = re.sub(r'<image\b[^>]*?xlink:href="data:image/png;base64,[^"]*"[^>]*?/>', "", svg)
    svg = svg.replace("background: transparent; background-color: transparent;",
                      "background: #FFFFFF; background-color: #FFFFFF;", 1)
    return re.sub(r"(<svg\b[^>]*>)", rf"\1<!-- {HASH_MARK}{digest} -->", svg, count=1)


def export(folder: Path) -> list[Finding]:
    cmd = drawio_command()
    if cmd is None:
        return [Finding("ERROR", "draw.io", "no encuentro la CLI de draw.io Desktop (drawio en el PATH o DRAWIO_BIN)")]
    drawio = drawio_file(folder)
    if drawio is None:
        return [Finding("ERROR", str(folder), "no hay ningún .drawio que exportar")]
    pages = ET.parse(drawio).getroot().findall("diagram")
    svg_dir = folder / "svg"
    svg_dir.mkdir(exist_ok=True)
    out: list[Finding] = []
    expected = set()
    for num, d in enumerate(pages, start=1):
        target = svg_dir / svg_name(num, d.get("id", f"pagina-{num}"))
        expected.add(target.name)
        result = subprocess.run(cmd + ["-x", "-f", "svg", "--svg-theme", "light", "-p", str(num), "-o", str(target),
                                       str(drawio)], capture_output=True, text=True, timeout=180, check=False)
        if not target.exists():
            out.append(Finding("ERROR", d.get("name", "?"), f"draw.io no generó el SVG: {result.stderr.strip()[-200:]}"))
            continue
        target.write_text(clean_svg(target.read_text(encoding="utf-8"), page_hash(d)), encoding="utf-8")
        print(f"Exportado: {target}")
    for old in svg_dir.glob("*.svg"):
        if old.name not in expected:
            old.unlink()
            print(f"Eliminado (ya no hay página): {old}")
    return out


def render(folder: Path, pages: list[int], out_dir: Path) -> list[Finding]:
    """Renderiza páginas a PNG para revisarlas visualmente (agentes que leen imágenes)."""
    cmd = drawio_command()
    drawio = drawio_file(folder)
    if cmd is None or drawio is None:
        return [Finding("ERROR", "render", "hace falta la CLI de draw.io y un .drawio")]
    total = len(ET.parse(drawio).getroot().findall("diagram"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[Finding] = []
    for num in pages or list(range(1, total + 1)):
        target = out_dir / f"pagina-{num:02d}.png"
        subprocess.run(cmd + ["-x", "-f", "png", "-p", str(num), "-o", str(target), str(drawio)],
                       capture_output=True, text=True, timeout=180, check=False)
        if target.exists():
            print(f"Renderizado: {target}")
        else:
            out.append(Finding("ERROR", f"página {num}", "draw.io no generó el PNG"))
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("check", "export", "render"):
        print(__doc__)
        return 2
    command, rest = argv[0], argv[1:]
    out_dir = Path(tempfile.gettempdir()) / "kiro-diagrams-render"
    if "--out" in rest:
        i = rest.index("--out")
        if i + 1 >= len(rest):
            print(__doc__)
            return 2
        out_dir, rest = Path(rest[i + 1]), rest[:i] + rest[i + 2:]
    folder = Path(rest[0]) if rest and not rest[0].isdigit() else DEFAULT_DIR
    if command == "check":
        findings = check(folder)
    elif command == "export":
        findings = export(folder)
    else:
        nums = [int(a) for a in rest if a.isdigit()]
        findings = render(folder, nums, out_dir)
    for f in findings:
        print(f)
    errors = [f for f in findings if f.level == "ERROR"]
    if command == "check" and not findings:
        print(f"OK: diagramas de {folder} al día y sin solapes")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
