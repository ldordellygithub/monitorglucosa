# 0006. Migraciones de base de datos con una Lambda `migrator` dentro de la VPC

- **Estado:** Aceptado
- **Fecha:** 2026-11-01
- **Decisiones relacionadas:** spec `fase-1a-infraestructura-y-auth` (D2, criterio 7.4); complementa ADR 0004 y ADR 0005

## Contexto

Aurora vive en subredes privadas, sin acceso público, y la VPC no tiene NAT Gateway (ADR 0004). Los runners de GitHub Actions no llegan a la base de datos, pero el pipeline debe aplicar las migraciones de Alembic antes de que la API sirva el digest nuevo (criterio 7.4). Las migraciones necesitan DDL, que la API no debe poder ejecutar (privilegio mínimo).

## Decisión

- Una segunda función Lambda, `monitorglucosa-migrator`, usa **la misma imagen** que la API con otro comando (`create_migrator_app`). Corre dentro de la VPC con su propio rol y su propio grupo de seguridad.
- El pipeline la invoca de forma **síncrona** tras el bootstrap SQL y antes de desplegar el digest nuevo de la API. Lambda Web Adapter entrega la invocación como `POST /events` (`AWS_LWA_PASS_THROUGH_PATH`); la comprobación de arranque usa `GET /`.
- Se conecta como `mg_migrator` (dueño del esquema `app`, con DDL) por TLS e IAM. La API usa `mg_api`, que solo tiene DML.
- Timeout de 300 s. Antes de invocarla, `deploy.py` espera con `aws lambda wait function-active-v2`, porque una función sin invocaciones durante semanas pasa a `Inactive`.
- Solo el rol de despliegue puede invocarla (`lambda:InvokeFunction`).
- Las migraciones deben ser compatibles con el digest anterior (expandir y luego contraer), porque la vuelta atrás solo revierte la API.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Migrar al arrancar la API | Concurrencia entre instancias, latencia de arranque en frío y DDL en el rol de la API |
| CodeBuild o ECS dentro de la VPC | Sin NAT necesitan endpoints de interfaz, con coste por hora y por zona |
| Alembic sobre RDS Data API | Dialecto no estándar y acoplamiento a una API de AWS (el ADR 0004 ya descartó Data API para los repositorios por ese acoplamiento) |
| Ejecutarlas a mano desde el equipo del propietario | Cada despliegue dependería de un paso manual y de acceso de red a Aurora |

## Consecuencias

- Una función más que mantener, sin coste en reposo.
- La prueba de humo y la vuelta atrás nunca revierten el esquema: si una migración no es retrocompatible, el despliegue puede dejar la API anterior sobre un esquema nuevo. La Property 6 comprueba que el digest nuevo solo se sirve si su migración terminó en `ok`; que la API anterior siga funcionando sobre el esquema nuevo depende de la regla de expandir y contraer.
- Se prueba con `upgrade head` → `downgrade base` → `upgrade head` contra PostgreSQL real en CI, y con el `Runner` falso de `deploy.py` para todas las combinaciones de fallo.

## Referencias

- [Lambda Web Adapter: código fuente (`src/lib.rs`)](https://github.com/awslabs/aws-lambda-web-adapter)
- [Imágenes de contenedor en Lambda: ciclo de vida de las funciones](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- ADR 0004: [Acceso de la API a Aurora sin NAT Gateway](0004-api-network-without-nat.md)
