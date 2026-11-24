# 0002. API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero

- **Estado:** Aceptado (coste pendiente de validar con la factura real; región actualizada de `sa-east-1` a `us-east-1` por [ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md))
- **Fecha:** registrado el 2026-11-01; precios de la instantánea del 2026-10-31; región actualizada el 2026-11-07
- **Decisión relacionada:** `T-3` (opción A1) y [ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md)

## Contexto

Restricciones: presupuesto de nube por debajo de US$20/mes, datos en `sa-east-1` (más cara que `us-east-1`) y un solo usuario, con uso esporádico (unas pocas sincronizaciones y consultas al día). El cómputo y la base de datos deben costar casi cero cuando nadie los usa.

## Decisión

- La API FastAPI corre en AWS Lambda, con Lambda Web Adapter, detrás de API Gateway HTTP API (ADR 0004).
- La base de datos es Aurora PostgreSQL Serverless v2 con `MinCapacity` 0 (pausa automática) y `SecondsUntilAutoPause` de 300 s.
- Versión: Aurora PostgreSQL 16, con versión menor ≥ 16.4. La pausa automática solo existe en versiones menores compatibles: AWS documenta 16.3 o superior, y un hilo de re:Post indica 16.4.

## Cifras (precios oficiales de lista de AWS en `us-east-1` tras [ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md) vs. `sa-east-1` original)

| Escenario | Coste estimado en `us-east-1` (vigente) | Coste en `sa-east-1` (anterior) |
| --- | --- | --- |
| A1 con uso bajo y escala a cero (`MinCapacity = 0`) + Secrets Manager (US$0,40/mes) + S3/ECR/CloudWatch | **≈ US$2–4/mes** | ≈ US$4/mes |
| A1 sin escala a cero (0,5 ACU continuos, 730 h/mes) | **≈ US$43,80/mes** (US$0,12/ACU-h) | ≈ US$91,25/mes (US$0,25/ACU-h) |
| Techo del presupuesto (~US$18/mes para ACU dentro del tope de US$20/mes) | **≈ 150 ACU-h/mes** | ≈ 79 ACU-h/mes |
| A2: contenedor + PostgreSQL de instancia fija | **> US$25–30/mes** (supera el tope de US$20/mes) | ≈ US$37–40/mes |

Claves KMS gestionadas por AWS (`aws/rds`, `aws/s3`, `aws/lambda`, `aws/secretsmanager`): US$0/mes de cuota fija; CloudFront y S3 con volumen monousuario: centavos de dólar al mes.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| A2: contenedor + PostgreSQL de instancia fija | Supera el presupuesto mensual de US$20/mes |
| Base de datos local | Descartada en `T-3` (impide acceso web y exige respaldo manual en un único disco) |
| Aurora sin escala a cero | ≈ US$43,80/mes en `us-east-1` (≈ US$91,25/mes en `sa-east-1`), por encima del presupuesto |

## Consecuencias

- La escala a cero es obligatoria. Cualquier conexión abierta impide la pausa (ADR 0004).
- Reanudar tarda unos 15 s, y 30 s o más tras 24 h en pausa. La NFR de latencia (p95 < 500 ms) se mide con la base de datos activa. La primera petición tras una pausa puede tardar hasta ~35 s, así que los clientes usan timeouts ≥ 40 s y muestran «despertando la base de datos».
- Terraform necesita el proveedor de AWS 5.81.0 o superior para `min_capacity = 0`. Con ese valor, `seconds_until_auto_pause` es obligatorio.
- Pendiente: validar el coste con la factura real y la alarma de AWS Budgets al 80 %.

## Referencias

- [Aurora Serverless v2: escala a cero con pausa automática](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
