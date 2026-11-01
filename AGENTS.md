# Instrucciones para agentes

Este proyecto usa desarrollo guiado por specs, al estilo de Kiro.

- Contexto permanente: `.kiro/steering/*.md` (product, tech, structure y los que añadas).
  Antes de proponer cambios, lee los que no tienen front matter o tienen `inclusion: always`.
  Los demás se cargan según su `inclusion` (`fileMatch`, `auto`, `manual`), como en Kiro.
  Cursor y VS Code generan rules/instructions `kiro-steering-*`: edita el steering, no esas copias.
- Cada funcionalidad vive en `.kiro/specs/<nombre>/` con `requirements.md`, `design.md` y
  `tasks.md` (o `bugfix.md` en lugar de `requirements.md` para un bug).
- Tres fases con aprobación del usuario entre una y otra. No avances de fase sin aprobación
  explícita y no escribas código de la funcionalidad durante las fases de spec.
- Criterios de aceptación en EARS: `WHEN <evento> THEN the system SHALL <respuesta>`.
- Cada tarea cita los requisitos que cubre: `_Requirements: X.Y_`.
- Comandos: `/spec-new`, `/spec-design`, `/spec-tasks`, `/spec-next`, `/spec-run`,
  `/spec-quick`, `/spec-bugfix`, `/spec-new-design-first`, `/spec-requirements`,
  `/spec-analyze`, `/spec-sync`, `/spec-converge`, `/spec-lint`, `/spec-status`, `/steering-generate`.
- Hooks del proyecto en `.kiro/hooks/*.json` (formato de Kiro 1.x; también se leen los `*.kiro.hook` de 0.x). Solo se ejecutan si el usuario
  los aprobó con `kspec hooks trust`; nunca ejecutes ese comando tú.
- Nunca leas ni escribas secretos. Respeta `.cursorignore`.
