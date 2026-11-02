# 0008. Rol de despliegue acotado con *permissions boundary* y pipeline público sin fugas

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisiones relacionadas:** spec `fase-1a-infraestructura-y-auth` (D4, criterio 7.2, NFR-4 y NFR-5); `tech.md · Seguridad (CI)`; `git.md` (A-7, U-6, U-7); complementa ADR 0005 y ADR 0007

## Contexto

Terraform crea roles IAM (los de las Lambdas), así que el rol que despliega necesita permisos de IAM. Un rol que puede crear roles sin límite puede escalar privilegios: crea un rol de administrador y lo asume. Además, el repositorio es público (`git.md`, A-7) y los logs de Actions lo son de hecho: GitHub los muestra a cualquier cuenta con sesión iniciada, también en repositorios públicos.

Datos verificados en la documentación oficial (2026-11-02):

- **Boundary:** los permisos efectivos de un rol son la intersección de sus políticas de identidad y su *permissions boundary*; un `Deny` explícito en cualquiera de las dos prevalece.
- **Delegación:** AWS documenta el patrón para delegar la creación de entidades: permitir las acciones de creación y de adjuntar políticas solo con la condición `iam:PermissionsBoundary` igual al boundary, y negar la edición de la política del boundary (`CreatePolicyVersion`, `DeletePolicy`, `DeletePolicyVersion`, `SetDefaultPolicyVersion`) y su retirada (`Delete…PermissionsBoundary`). El ejemplo de AWS es para usuarios; aquí se aplica a roles con las acciones equivalentes.
- **Límite del boundary:** no acota las políticas de recursos que conceden permisos directamente a la sesión de un rol.
- **OIDC de GitHub:** con un entorno, el `sub` es `repo:ORG/REPO:environment:NOMBRE`; el `aud` es `sts.amazonaws.com`; el job necesita `id-token: write`. GitHub exige definir al menos una condición en la política de confianza.
- **Logs de Actions:** la redacción de secretos «no está garantizada»; los datos estructurados (JSON, YAML) la hacen fallar; los valores sensibles que no son secretos de GitHub se enmascaran con `::add-mask::`; si algo se filtra, GitHub indica borrar el log y rotar el secreto.
- **Terraform `sensitive`:** oculta el valor en la salida de la CLI (`(sensitive value)`), pero lo guarda en claro en el estado y en los archivos de plan.
- **Recursos no acotables:** `ecr:GetAuthorizationToken` no admite recurso (los ejemplos de AWS lo separan con `Resource: "*"`). Para conectar una Lambda a una VPC, AWS exige seis permisos de EC2 sobre `"*"`: `CreateNetworkInterface`, `DescribeNetworkInterfaces`, `DescribeSubnets`, `DeleteNetworkInterface`, `AssignPrivateIpAddresses` y `UnassignPrivateIpAddresses`.
- **`aws:RequestedRegion`:** controla el endpoint que se invoca, no el efecto de la operación. IAM, CloudFront y Budgets son servicios globales con un único endpoint en `us-east-1`: una condición que exija `sa-east-1` los denegaría, así que AWS indica excluirlos.

## Decisión

**Rol de despliegue `monitorglucosa-deploy`:**

- Confianza (7.2): proveedor OIDC de GitHub con `sub` = `repo:ldordellygithub/monitorglucosa:environment:prod` y `aud` = `sts.amazonaws.com`. Ningún otro entorno, rama ni repositorio puede asumirlo.
- Crea o modifica roles solo si llevan el boundary `monitorglucosa-workload-boundary`: `iam:CreateRole`, `iam:PutRolePolicy`, `iam:AttachRolePolicy` y `iam:PutRolePermissionsBoundary` con la condición `iam:PermissionsBoundary`.
- `Deny` explícito sobre editar o borrar la política del boundary, sobre retirar el boundary de un rol (`iam:DeleteRolePermissionsBoundary`) y sobre modificar el propio rol de despliegue.
- No tiene boundary propio, porque es quien lo impone. Su poder lo limitan su política y esos `Deny`.
- Alcance por prefijo de nombre `monitorglucosa-` y por `aws:RequestedRegion` = `sa-east-1`, salvo IAM, CloudFront y Budgets, que son servicios globales con endpoint en `us-east-1`.
- Solo recibe los permisos operativos que el diseño enumera: estado en S3, push a ECR, invocar el `migrator`, `execute-api:Invoke` en `GET /health/ready`, `rds-data:ExecuteStatement` y `secretsmanager:GetSecretValue` sobre el clúster y el secreto exactos (ADR 0007), y `ssm:GetParameter` del correo.

**Excepciones a NFR-4** (`Action`/`Resource` sin acotar, porque AWS no lo permite). Cada una lleva un comentario con su motivo y una supresión con nombre en checkov:

1. `ecr:GetAuthorizationToken`.
2. Las seis acciones de EC2 de los roles de las Lambdas `api` y `migrator` (no del rol de despliegue), listadas arriba. El diseño enumeraba tres; la documentación exige seis, y esta lista es la que prevalece.
3. Las acciones de solo lectura `Describe*` y `List*` que Terraform necesita para refrescar el estado, enumeradas una por una en el código, nunca con comodín. Incluye las comprobaciones de red que Lambda hace con el rol de quien despliega (`ec2:DescribeSecurityGroups`, `ec2:DescribeSubnets`, `ec2:DescribeVpcs` y `ec2:GetSecurityGroupsForVpc`).

**Pipeline público sin fugas (NFR-5):**

- El ARN del rol y el nombre del bucket de estado son secretos del entorno `prod`, así que GitHub los enmascara.
- `deploy.py` enmascara el ID de cuenta con `::add-mask::`, porque no es un secreto de GitHub.
- Terraform escribe en el log solo el resumen del plan. Los outputs sensibles se marcan `sensitive`. No se suben planes como artefactos, porque contienen los valores sensibles en claro.
- Ningún secreto se empaqueta en JSON ni YAML.
- Las acciones van fijadas por SHA, con `contents: read` (U-6). `id-token: write` solo en el job `deploy`.
- Si un valor llegara a un log: borrar el log y rotar el valor afectado.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| `AdministratorAccess` para el rol de despliegue | Contradice el mínimo privilegio y permite escalar privilegios |
| Un rol de solo lectura para `terraform plan` en los PR | Exige otra condición de confianza, distinta de la decidida en `tech.md` (solo el entorno `prod`) |

## Consecuencias

- El propietario aprueba el despliegue sin ver el plan completo en GitHub; lo revisa con `terraform plan` en local.
- Cada servicio nuevo exige ampliar el boundary y la política de despliegue; olvidarlo hace fallar el `apply` en vez de abrir un hueco.
- Como el rol de despliegue no puede modificarse a sí mismo ni al boundary, cualquier cambio en esos recursos (módulo `bootstrap`) solo lo aplica el administrador desde local, no el pipeline.
- La redacción de GitHub no está garantizada: la defensa principal es no imprimir valores sensibles, no confiar en el enmascarado. El primer despliegue real es la prueba: se revisa su log público en busca de ID de cuenta y ARN.
- El boundary no acota las políticas de recursos que conceden acceso directo a una sesión del rol: cada política de recursos nueva (ECR, S3, Secrets Manager) se revisa por separado.
- Los permisos de EC2 de las Lambdas en una VPC se conceden también, de forma implícita, al código de la función. AWS recomienda un `Deny` con la condición `lambda:SourceFunctionArn` para que solo los use el servicio de Lambda. Se decide al implementar el módulo `api` (tarea 18).
- Se prueba con `terraform test` (la política de confianza solo acepta ese `sub` y ese `aud`; los roles de las Lambdas llevan el boundary), con checkov (sin `*` salvo las excepciones con nombre) y con gitleaks y semgrep en CI. `terraform test` usa proveedores simulados: comprueba el contenido de las políticas, no cómo las evalúa AWS; eso solo lo confirma el primer `apply`. Que ningún log público muestre datos de la cuenta solo se comprueba a mano en el primer despliegue.

## Referencias

- [Permissions boundaries para entidades de IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Clave de condición `aws:RequestedRegion`](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html)
- [Denegar según la región solicitada: servicios globales en `us-east-1`](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_aws_deny-requested-region.html)
- [OIDC de GitHub Actions en AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [Uso seguro de GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [Ver los logs de una ejecución de workflow](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)
- [Terraform: gestión de datos sensibles](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
- [Ejemplos de políticas de identidad de Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/security_iam_id-based-policy-examples.html)
- [Lambda: acceso a recursos de una VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- ADR 0005: [Entorno local con Docker y la misma imagen de la API en Lambda](0005-containerized-local-environment.md)
- ADR 0007: [Bootstrap SQL idempotente por RDS Data API](0007-idempotent-sql-bootstrap-through-rds-data-api.md)
