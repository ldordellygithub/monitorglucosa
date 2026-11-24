# Guía de desarrollo — monitorglucosa

Reglas, comandos reales y runbook de primer despliegue para trabajar en este repositorio. La estrategia completa y su
porqué están en [.kiro/steering/git.md](../.kiro/steering/git.md); las convenciones de código, en
[structure.md](../.kiro/steering/structure.md); el contrato de la API publicada, en [docs/api/README.md](api/README.md).
Los comandos marcados «(previsto)» corresponden a componentes de specs futuras (`collector/`, `frontend/`).

## Reglas

1. `main` siempre desplegable: nada se sube directo; todo entra por Pull Request con CI en verde.
2. Una rama por spec (`feature/<spec>`; `fix/<spec>` para un bug), corta y desde `main`.
3. Un commit por tarea de `tasks.md`, en Conventional Commits, con el trailer `Refs: <spec>#<tarea>` y las pruebas en verde.
   Con merge por rebase, cada commit llega tal cual a `main`.
4. Cada prueba que verifica un criterio lleva su etiqueta `req`; `docs/traceability.md` se commitea al día.
5. El repositorio es **público**: nunca secretos, `.env`, lecturas reales del GD50 ni datos personales; solo datos
   sintéticos en pruebas y ejemplos.
6. El merge lo hace Luis con «Rebase and merge»; cada despliegue a `prod` espera su aprobación manual en GitHub
   (fuera de la ventana crítica diaria `20:00–23:00` COT).
7. Al cerrar una fase, tag SemVer (`v0.1.0` = fase 1) con su nota de versión.

## Preparar el entorno local (una vez)

```bash
# Herramientas base (Ubuntu 24.04/26.04)
sudo apt install gh                                   # GitHub CLI (PR, checks y configuración)
gh auth login                                         # sesión de GitHub en esta máquina
git clone https://github.com/ldordellygithub/monitorglucosa.git && cd monitorglucosa

# Hooks locales (commit, commit-msg y pre-push)
pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
kspec doctor                                          # comprueba el kit Kiro

# Dependencias Python fijadas (--locked; Python 3.13, uv 0.13.5)
uv --directory backend sync --locked
uv --directory dev/jwt-issuer sync --locked
uv --directory scripts sync --locked

# Entorno local completo con Docker Compose (API + PostgreSQL 16 + emisor JWT)
cp .env.example .env
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8000/health

# Componentes de specs futuras
uv --directory collector sync --locked                # (previsto, fase-1b)
npm --prefix frontend ci                              # (previsto, fase-2)
```

## Swagger UI, ReDoc y pruebas interactivas en local

En `ENVIRONMENT=local` (y `test`), FastAPI expone documentación interactiva automáticamente; en `prod` los tres
endpoints están desactivados (`docs_url = None`, `redoc_url = None`, `openapi_url = None`; D17):

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **Esquema OpenAPI 3.1 en vivo:** `http://127.0.0.1:8000/openapi.json`

Para probar rutas protegidas (`/api/v1/me`) en Swagger UI o con `curl` usando el emisor JWT local (`dev/jwt-issuer`):

```bash
# 1) Pedir un access token sintético válido al emisor local
TOKEN="$(curl -fsS -X POST http://127.0.0.1:9000/token \
  -H 'Content-Type: application/json' \
  -d '{"sub":"8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f","client_id":"web"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

# 2) Invocar /api/v1/me (o pegar TOKEN en el botón "Authorize" de Swagger UI)
curl -fsS http://127.0.0.1:8000/api/v1/me -H "Authorization: Bearer ${TOKEN}"

# 3) Regenerar o comprobar que backend/openapi.json y docs/api/README.md están al día
uv --directory backend run python tools/export_openapi.py --check
```

## Runbook de primer despliegue en AWS (`us-east-1`)

Se ejecuta una sola vez por el propietario (ver [design.md · Primer despliegue](../.kiro/specs/fase-1a-infraestructura-y-auth/design.md#primer-despliegue-bootstrap),
[ADR 0007](adr/0007-idempotent-sql-bootstrap-through-rds-data-api.md),
[ADR 0008](adr/0008-scoped-deployment-role-and-leak-free-pipeline.md) y
[ADR 0011](adr/0011-aws-region-us-east-1-for-cost-optimization.md)).

### Paso 0 — Cuenta exclusiva de AWS (consola web)
1. Crear una cuenta de AWS dedicada exclusivamente a `monitorglucosa` (el presupuesto de US$20/mes mide toda la cuenta).
2. Activar **MFA TOTP** en el usuario raíz y **no crear claves de acceso (`access keys`)** para el usuario raíz.
3. Con el usuario raíz, ir a **Account Settings → IAM User and Role Access to Billing Information** y activar el acceso
   (requisito de AWS para que `monitorglucosa-deploy` pueda crear y consultar `aws_budgets_budget`).
4. Habilitar **IAM Identity Center (SSO)** en `us-east-1` y crear un usuario administrador con MFA para el bootstrap y emergencias.

### Paso 1 — Herramientas locales
Verificar las herramientas instaladas en el equipo local:

```bash
aws --version                  # AWS CLI v2
terraform version | head -n 1  # Terraform v1.16.6
docker --version               # Docker Engine
uv --version                   # uv 0.13.5
actionlint -version | head -n 1
gitleaks version
```

Iniciar sesión administrativa temporal vía SSO:

```bash
aws configure sso              # una sola vez: región us-east-1, perfil ej. mg-admin
aws sso login --profile mg-admin
export AWS_PROFILE=mg-admin
export AWS_REGION=us-east-1
aws sts get-caller-identity    # confirmar cuenta exclusiva
```

### Paso 2 — Guardar el correo del propietario en Parameter Store (D11)
El correo nunca entra al repositorio ni a los logs públicos; lo leen Cognito, SNS y Budgets desde SSM `SecureString`:

```bash
read -r -p "Correo del propietario para Cognito, SNS y Budgets: " OWNER_EMAIL
aws ssm put-parameter \
  --region us-east-1 \
  --name /monitorglucosa/prod/owner-email \
  --type SecureString \
  --value "${OWNER_EMAIL}" \
  --overwrite
unset OWNER_EMAIL
```

### Paso 3 — Bootstrap inicial de Terraform (`module.bootstrap`)
Crear el override temporal local (`infra/terraform/backend_override.tf`, ignorado por `.gitignore`) para crear el
bucket del estado remoto, el proveedor OIDC de GitHub, el rol `monitorglucosa-deploy`, el *permissions boundary* y ECR:

```bash
cat > infra/terraform/backend_override.tf <<'HCL'
terraform {
  backend "local" {}
}
HCL

terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -target=module.bootstrap
terraform -chdir=infra/terraform apply -target=module.bootstrap
```

### Paso 4 — Migrar el estado al backend remoto S3 (`use_lockfile = true`)
```bash
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
TF_STATE_BUCKET="monitorglucosa-tfstate-${ACCOUNT_ID}"
DEPLOY_ROLE_ARN="$(terraform -chdir=infra/terraform output -raw deploy_role_arn)"

rm -f infra/terraform/backend_override.tf
terraform -chdir=infra/terraform init \
  -migrate-state \
  -backend-config="bucket=${TF_STATE_BUCKET}"
```

### Paso 5 — Configurar secretos del entorno `prod` y reglas en GitHub
1. Cargar los dos secretos del entorno `prod` (nunca en el repositorio):

```bash
gh secret set AWS_DEPLOY_ROLE_ARN --env prod --body "${DEPLOY_ROLE_ARN}"
gh secret set TF_STATE_BUCKET --env prod --body "${TF_STATE_BUCKET}"
unset ACCOUNT_ID TF_STATE_BUCKET DEPLOY_ROLE_ARN
```

2. Confirmar que el entorno `prod` exige revisión manual (`G-2` ya aplicada) y sincronizar el ruleset `main` con el check `ci`:

```bash
gh api repos/ldordellygithub/monitorglucosa/environments/prod --jq '{name, rules: [.protection_rules[].type]}'
kspec github plan
# Solo tras revisar el plan y confirmar:
kspec github apply --yes
```

### Paso 6 — Primer despliegue vía GitHub Actions (`deploy.yml`)
1. Al fusionar el PR en `main`, `.github/workflows/deploy.yml` ejecuta `build` (construye la imagen `linux/amd64`, la
   prueba con Docker Compose y E2E, y guarda el artefacto con su `SHA-256`).
2. El job `deploy` se detiene esperando tu aprobación manual en **GitHub → Actions → deploy → Review deployments**
   (aprobar fuera de la ventana crítica `20:00–23:00` COT).
3. Tras aprobar, `deploy` asume `monitorglucosa-deploy` por OIDC, sube la imagen por digest inmutable a ECR y ejecuta
   `scripts/deploy.py`: Fase 1 Terraform → `db_bootstrap.py` (Data API) → Lambda `migrator` → Fase 2 Terraform →
   `smoke_test.py` (`/health/ready` SigV4 + `/api/v1/me` → 401) con vuelta atrás automática a `D_prev` si falla.

### Paso 7 — Verificación post-despliegue, presupuesto y alertas de coste
1. Confirmar el correo de suscripción al tema SNS `monitorglucosa-alarms`.
2. Iniciar sesión por primera vez en Cognito Hosted UI con la contraseña temporal recibida por correo y activar **MFA TOTP**.
3. **Presupuesto y respuesta ante sobrecostes (Req 8.3, NFR-3, D14):**
   - Estimación base en `us-east-1`: **≈ US$2,75/mes** (techo mensual objetivo: **< US$20/mes**).
   - **AWS Budgets** envía avisos al correo de SSM cuando el gasto real o previsto de toda la cuenta supera:
     - **80 % (US$16/mes):** revisar métricas de Aurora (`ServerlessDatabaseCapacity`) y Cost Explorer.
     - **100 % (US$20/mes):** detener cargas no esenciales e investigar la causa de inmediato.
   - **Techo puntual de alerta en runbook: US$30/mes** (límite máximo admisible ante una anomalía puntual antes de
     aplicar contención de emergencia; la alarma `monitorglucosa-aurora-not-paused` avisa a las 6 h si Aurora no baja a 0 ACU).
4. Completar y registrar con fecha y evidencia todas las comprobaciones de
   [.kiro/specs/fase-1a-infraestructura-y-auth/manual-checks.md](../.kiro/specs/fase-1a-infraestructura-y-auth/manual-checks.md).

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
kspec steering check               # valida steering sin LLM
kspec steering-sync                # sincroniza reglas/instructions tras aprobar cambios en steering
kspec adr new "<título>"           # nueva decisión de arquitectura
kspec github plan                  # diferencias entre .github/ y GitHub (solo lectura)
kspec github apply --yes           # aplica la configuración de GitHub (solo tras revisar el plan)
```

## Calidad, pruebas y seguridad

| Momento | Qué se comprueba | Comando a mano |
| --- | --- | --- |
| Commit | gitleaks, formato, ruff, rama `main` protegida, lint de specs, `traceability.md` | `pre-commit run --all-files` |
| Mensaje | Conventional Commits | (automático en `git commit`) |
| Push | `mypy` y pruebas del backend; push protection de GitHub bloquea secretos | `pre-commit run --hook-stage pre-push --all-files` |
| Pull Request | `spec-lint`, `architecture`, `traceability`, `pr-title` y `ci` | `gh pr checks` |
| Semanal | PR de Dependabot y alertas de seguridad | `gh pr list --author app/dependabot` |

Comandos reales del stack (Fase 1A):

```bash
# Backend: lint, formato, tipos estrictos, arquitectura, cobertura >= 80 % y contrato OpenAPI
uv --directory backend run ruff check .
uv --directory backend run ruff format --check .
uv --directory backend run mypy
uv --directory backend run lint-imports
uv --directory backend run pytest -m "not e2e" --cov --cov-fail-under=80
uv --directory backend run python tools/export_openapi.py --check
uv --directory backend run openapi-spec-validator openapi.json

# Emisor JWT local y scripts de despliegue
uv --directory dev/jwt-issuer run ruff check . && uv --directory dev/jwt-issuer run mypy && uv --directory dev/jwt-issuer run pytest
uv --directory scripts run ruff check . && uv --directory scripts run mypy && uv --directory scripts run pytest

# Imagen única y pruebas E2E con Docker Compose
docker build --platform linux/amd64 --provenance=false --sbom=false -t monitorglucosa-api:local backend
docker compose up -d --build --wait
uv --directory backend run pytest -m e2e
docker compose down -v --remove-orphans

# Infraestructura Terraform (offline con proveedores simulados) y Checkov
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform init -backend=false -input=false
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform test
docker run --rm -v "$PWD:/workspace:ro" \
  bridgecrew/checkov:3.2.517@sha256:34c97d3e49a6003bbf11ab5353ebcf609cdba95b94d09f61983bdf683035a967 \
  -d /workspace/infra/terraform --framework terraform --compact --quiet

# Seguridad y workflows en local
actionlint .github/workflows/*.yml
gitleaks detect --source . --no-banner --redact
semgrep scan --config p/owasp-top-ten --config p/python --error --metrics=off --exclude scripts/tests backend/src backend/tools dev/jwt-issuer/src scripts

# Frontend (previsto, fase-2)
npm --prefix frontend ci && npm --prefix frontend test
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
- Commitear `.env`, `infra/terraform/backend_override.tf`, credenciales, lecturas reales del GD50, datos personales o volcados de la base de datos.
- Fusionar con un check en rojo o saltarse los hooks con `--no-verify`.
- Aprobar un despliegue a `prod` sin haber visto el resultado de CI del commit que se despliega o dentro de la ventana crítica `20:00–23:00` COT.
