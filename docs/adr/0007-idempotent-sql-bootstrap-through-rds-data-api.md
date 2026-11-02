# 0007. Bootstrap SQL idempotente por RDS Data API

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisiones relacionadas:** spec `fase-1a-infraestructura-y-auth` (D3, criterios 5.3 y 7.4); precisa el alcance del ADR 0004 y complementa el ADR 0006; `T-10` y `T-11`

## Contexto

La autenticación IAM de la API (ADR 0004) exige usuarios de base de datos miembros de `rds_iam` (`mg_api` y `mg_migrator`). Crearlos requiere al usuario maestro de Aurora, cuya contraseña gestiona RDS en Secrets Manager y rota cada 7 días por defecto. Sin NAT, la Lambda no llega a Secrets Manager, y un endpoint de interfaz cobra por hora y por zona. Las variables de entorno de la Lambda no pueden contener secretos (`T-11`). Los runners de GitHub Actions sí tienen red pública, pero no llegan a Aurora por TCP.

Datos verificados en la documentación de AWS (2026-11-02):

- Data API ejecuta SQL por HTTPS, sin conexión TCP, con las credenciales de un secreto de Secrets Manager (`secretArn`).
- Data API no admite varias sentencias en una llamada («Multi-statements aren't supported»).
- Una petición a un clúster en pausa falla con `DatabaseResumingException` y reanuda la instancia; `DatabaseUnavailableException` indica que el escritor no está disponible.
- En Aurora PostgreSQL 14 o superior, Data API solo admite contraseñas `scram-sha-256`.
- El SQL de una llamada tiene un máximo de 65 536 caracteres, y AWS recomienda `continueAfterTimeout` para DDL.
- El ARN de un secreto creado por RDS tiene la forma `rds!cluster-…`; la documentación de `ExecuteStatement` lo menciona al hablar de `secretArn`.

## Decisión

- `scripts/db_bootstrap.py` ejecuta, en cada despliegue y antes de migrar, un único bloque `DO $$ … $$` con `rds-data execute-statement`, el ARN del secreto maestro gestionado por RDS y `continueAfterTimeout = true`. Ante `DatabaseResumingException` o `DatabaseUnavailableException` reintenta con espera exponencial hasta 120 s.
- Se espera que Data API acepte un bloque `DO` como una sola sentencia, porque los `;` quedan dentro del cuerpo entrecomillado con `$$` (inferencia sin respaldo documental: ver la verificación bloqueante). El bloque pesa mucho menos de 65 536 caracteres.
- El bloque es idempotente: crea `mg_migrator` y `mg_api` (con `rds_iam`), el esquema `app` y los privilegios por defecto. Nunca toca datos. La Property 7 comprueba que `n` ejecuciones dejan el mismo estado.
- En local, `dev/postgres/init/` ejecuta el mismo archivo como `mg_admin`, un rol sin superusuario que imita al maestro de RDS.
- El rol de despliegue recibe `rds-data:ExecuteStatement` sobre el ARN del clúster y `secretsmanager:GetSecretValue` sobre el ARN exacto del secreto maestro (`rds!cluster-…`), nunca un patrón como `rds-db-credentials/*`. Las Lambdas no tienen ningún permiso sobre Secrets Manager.
- **Alcance del ADR 0004:** ese ADR descartó Data API como ruta de datos de la API (Lambda fuera de la VPC, repositorios acoplados a una API de AWS). Este ADR la usa solo desde el pipeline, para crear roles; la API sigue conectándose por TCP con TLS e IAM.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Ejecutar el bootstrap a mano una vez | Cada despliegue dependería de un paso manual, y un clúster restaurado necesitaría repetirlo |
| Endpoint de interfaz de Secrets Manager dentro de la VPC | Coste por hora y por zona, para un uso de unos segundos por despliegue |
| Contraseña maestra en variables de entorno de la Lambda | Lo prohíbe `T-11`: son visibles con `lambda:GetFunctionConfiguration`, y la contraseña rota cada 7 días |

## Consecuencias

- Data API queda activado en el clúster (US$0,70 por millón de llamadas; menos de 100 por mes en este uso).
- No amplía el poder del rol de despliegue: ya puede cambiar la contraseña maestra con `ModifyDBCluster`.
- Cada llamada lee el secreto vigente, así que la rotación de 7 días no afecta al bootstrap.
- Cada despliegue puede despertar a Aurora, algo que la migración posterior necesita de todos modos.
- **Verificación bloqueante, antes de dar por buena la ruta:** AWS no afirma de forma explícita las tres cosas siguientes, que se comprueban en el primer despliegue real, porque no se pueden probar en local:
  1. Data API acepta el secreto gestionado por RDS (`manage_master_user_password`). La documentación solo lo sugiere de forma indirecta.
  2. Un bloque `DO $$ … $$` se acepta como una sola sentencia. Es una inferencia, no algo documentado.
  3. La contraseña maestra generada por RDS es compatible con el requisito `scram-sha-256` de Data API.
- Si alguna falla, el despliegue falla antes de migrar, la API en servicio no cambia y el diseño se replantea con el propietario. El resultado observado se registra en `manual-checks.md`.
- Lo que sí se prueba en CI: el SQL ejecutado 3 veces como `mg_admin` contra PostgreSQL 16 real (idempotencia, `mg_api` sin `CREATE TABLE`) y `db_bootstrap.py` con dobles de la CLI de AWS, incluidos los reintentos.

## Referencias

- [Limitaciones de RDS Data API](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.limitations.html)
- [Solución de problemas de RDS Data API: multi-sentencias](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.troubleshooting.html)
- [Autorización de acceso a RDS Data API y secretos](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.access.html)
- [API `ExecuteStatement` de RDS Data API](https://docs.aws.amazon.com/rdsdataservice/latest/APIReference/API_ExecuteStatement.html)
- [Contraseñas de usuario maestro con Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-secrets-manager.html)
- [Aurora Serverless v2: pausa automática](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
- ADR 0004: [Acceso de la API a Aurora sin NAT Gateway](0004-api-network-without-nat.md)
- ADR 0006: [Migraciones con una Lambda `migrator` dentro de la VPC](0006-database-migrations-with-an-in-vpc-migrator-lambda.md)
