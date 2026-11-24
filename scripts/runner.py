"""Interfaz `Runner` inyectable para ejecutar comandos externos (terraform, aws).

Separa la ejecución de procesos del flujo de despliegue y del bootstrap SQL para
poder probar todas las combinaciones de éxito y fallo con dobles deterministas.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    """Resultado inmutable de un comando externo."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    """Puerto de ejecución de subprocesos (sin shell)."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        """Ejecuta `command` y devuelve código de salida, stdout y stderr."""
        ...


class SubprocessRunner:
    """Implementación real de `Runner` sobre `subprocess.run` sin shell."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        """Ejecuta el comando en forma de lista de argumentos (nunca `shell=True`)."""
        if not command:
            raise ValueError("El comando a ejecutar no puede estar vacío.")

        merged_env: dict[str, str] | None = None
        if env is not None:
            merged_env = {**os.environ, **env}

        try:
            completed = subprocess.run(  # noqa: S603
                list(command),
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd,
                env=merged_env,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            suffix = f"timeout tras {timeout_s}s"
            full_stderr = f"{stderr}\n{suffix}".strip() if stderr else suffix
            return CommandResult(returncode=124, stdout=stdout, stderr=full_stderr)

        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
