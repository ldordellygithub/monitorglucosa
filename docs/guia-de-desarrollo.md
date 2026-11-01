# Guía de desarrollo — monitorglucosa

Reglas y comandos para trabajar en este repositorio. La estrategia completa y su porqué están en
[.kiro/steering/git.md](../.kiro/steering/git.md); las convenciones de código, en
[structure.md](../.kiro/steering/structure.md). Los comandos marcados «(previsto)» aún no existen: se confirman cuando
la spec que crea ese componente los añada a `tech.md`.

## Reglas

1. `main` siempre desplegable: nada se sube directo; todo entra por Pull Request con CI en verde.
2. Una rama por spec (`feature/<spec>`; `fix/<spec>` para un bug), corta y desde `main`.
3. Un commit por tarea de `tasks.md`, en Conventional Commits, con el trailer `Refs: <spec>#<tarea>` y las pruebas en verde.
   Con merge por rebase, cada commit llega tal cual a `main`.
4. Cada prueba que verifica un criterio lleva su etiqueta `req`; `docs/traceability.md` se commitea al día.
5. El repositorio es **público**: nunca secretos, `.env`, lecturas reales del GD50 ni datos personales; solo datos
   sintéticos en pruebas y ejemplos.
6. El merge lo hace Luis con «Rebase and merge»; cada despliegue a `prod` espera su aprobación en GitHub.
7. Al cerrar una fase, tag SemVer (`v0.1.0` = fase 1) con su nota de versión.

## Preparar el entorno (una vez)

```bash
sudo apt install gh                # GitHub CLI (PR, checks y configuración del repositorio)
gh auth login                      # sesión de GitHub en esta máquina
git clone https://github.com/<propietario>/monitorglucosa.git && cd monitorglucosa
pre-commit install                 # hooks de commit, mensaje y push (tras /precommit-setup)
kspec doctor                       # comprueba el kit Kiro
uv sync --directory backend        # (previsto) dependencias del backend
uv sync --directory collector      # (previsto) dependencias del colector
docker compose up -d               # (previsto) API, PostgreSQL 16, web y emisor JWT de pruebas
```

## Flujo de una funcionalidad con Kiro

| Paso | Comando | Qué pasa |
| --- | --- | --- |
| 1. Partir de `main` al día | `git switch main && git pull --ff-only` | |
| 2. Requisitos | `/kiro:spec-new <funcionalidad>` | Exige la fundación (`kspec foundation`) |
| 3. Rama de la spec | `git switch -c feature/<spec>` | `/kiro:spec-next` la propone si no existe |
| 4. Diseño y tareas | `/kiro:spec-design` → `/kiro:spec-tasks` | Apruebas cada fase con «aprobado» |
| 5. Implementar | `/kiro:spec-next` (una tarea) o `/kiro:spec-run` | Pruebas etiquetadas y matriz regenerada |
| 6. Commit de la tarea | lo propone el agente; con tu sí, `git add` + `git commit` | Mensaje con `Refs: <spec>#<tarea>` |
| 7. Comprobar la spec | `/kiro:spec-converge` | «Convergencia: completa» |
| 8. Pull Request | `/kiro:spec-pr` | Push y `gh pr create` con tu confirmación |
| 9. Fusionar | `gh pr merge --rebase --delete-branch` | Con todos los checks en verde |
| 10. Aprobar el despliegue | GitHub → Actions → el job de `prod` → «Review deployments» | Solo tú; prueba de humo y vuelta atrás automáticas |
| 11. Limpiar | `git switch main && git pull --ff-only && git branch -d feature/<spec>` | |

Si la spec supera ~400 líneas de código sin contar pruebas, abre un PR por ola de `Execution Order`.

## Git

```bash
git status                         # qué cambió
git diff                           # cambios sin preparar; --staged para los preparados
git log --oneline --graph -20      # historial reciente
git log --format='%h %s%n  %(trailers:key=Refs,valueonly)' -10   # commits con su tarea
git pull --rebase origin main      # actualizar la rama con main (historial lineal)
git push -u origin feature/<spec>  # primera subida de la rama
git push --force-with-lease        # solo en tu rama, tras un rebase; nunca en main
```

## GitHub CLI

```bash
gh repo view --web                 # abrir el repositorio
gh pr status                       # PR abiertos y su CI
gh pr checks                       # estado de los checks del PR actual
gh pr view --web                   # abrir el PR en el navegador
gh run watch                       # seguir la ejecución de CI en vivo
gh release create v0.1.0 --title "Fase 1" --notes-file <nota.md>   # release al cerrar una fase
```

## Kit Kiro

```bash
kspec status                       # specs, aprobaciones, fundación, arquitectura y trazabilidad
kspec foundation                   # qué falta antes de la primera spec
kspec lint <spec>                  # estructura y trazabilidad de una spec
kspec trace                        # regenera docs/traceability.md
kspec trace check                  # matriz al día, sin pruebas huérfanas
kspec trace --commits [spec]       # criterio → tareas → commits
kspec diagrams check               # documentación arquitectónica al día
kspec adr new "<título>"           # nueva decisión de arquitectura
kspec github plan                  # diferencias entre .github/ y GitHub (solo lectura)
kspec github apply --yes           # aplica la configuración de GitHub (solo tras revisar el plan)
```

## Calidad, pruebas y seguridad

| Momento | Qué se comprueba | Comando a mano |
| --- | --- | --- |
| Commit | gitleaks, formato, ruff, rama `main` protegida, lint de specs | `pre-commit run --all-files` |
| Mensaje | Conventional Commits | (automático en `git commit`) |
| Push | Pruebas; push protection de GitHub bloquea secretos | `pre-commit run --hook-stage pre-push --all-files` |
| Pull Request | `spec-lint`, `architecture`, `traceability`, `pr-title` y, cuando exista, `ci` | `gh pr checks` |
| Semanal | PR de Dependabot y alertas de seguridad | `gh pr list --author app/dependabot` |

Comandos del stack (todos «previsto» hasta que existan sus componentes):

```bash
uv run --directory backend ruff check . && uv run --directory backend ruff format --check .
uv run --directory backend mypy --strict src
uv run --directory backend pytest --cov=src
npm --prefix frontend ci && npm --prefix frontend test
docker compose build && docker compose up -d
terraform -chdir=infra/terraform fmt -check && terraform -chdir=infra/terraform validate
```

## Releases

Al cumplir el criterio de «hecho» de una fase en `product.md`:

```bash
git switch main && git pull --ff-only
git tag -a v0.1.0 -m "Fase 1: sincronización, registro e historial"
git push origin v0.1.0
gh release create v0.1.0 --title "Fase 1" --notes-file <nota.md>
```

`v0.1.0` fase 1, `v0.2.0` fase 2, `v1.0.0` MVP (fase 3). Una corrección posterior: `v0.1.1`.

## Recuperar errores

| Situación | Comando |
| --- | --- |
| Deshacer el último commit sin perder cambios (aún sin push) | `git reset --soft HEAD~1` |
| Corregir el mensaje del último commit (aún sin push) | `git commit --amend` |
| Revertir un commit ya fusionado en `main` | `git revert <sha>` en una rama `fix/…` y PR |
| Resolver un conflicto al actualizar con `main` | editar, `git add <archivo>` y `git rebase --continue` |
| Abandonar un rebase a medias | `git rebase --abort` |
| Recuperar algo «perdido» | `git reflog` y `git switch -c rescate <sha>` |
| Un secreto llegó a un commit | No hagas push. Rota el secreto y reescribe solo tu rama; si ya está en GitHub, rótalo de inmediato: el historial público no se limpia |

## Nunca

- Push directo o `--force` sobre `main`.
- Commitear `.env`, credenciales, lecturas reales del GD50, datos personales o volcados de la base de datos.
- Fusionar con un check en rojo o saltarse los hooks con `--no-verify`.
- Aprobar un despliegue a `prod` sin haber visto el resultado de CI del commit que se despliega.
