# 0002. API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero

- **Estado:** Aceptado (coste pendiente de validar con la factura real)
- **Fecha:** registrado el 2026-11-01; precios de la instantánea del 2026-10-31
- **Decisión relacionada:** `T-3` (opción A1)

## Contexto

Restricciones: presupuesto de nube por debajo de US$20/mes, datos en `sa-east-1` (más cara que `us-east-1`) y un solo usuario, con uso esporádico (unas pocas sincronizaciones y consultas al día). El cómputo y la base de datos deben costar casi cero cuando nadie los usa.

## Decisión

- La API FastAPI corre en AWS Lambda, con Lambda Web Adapter, detrás de API Gateway HTTP API (ADR 0004).
- La base de datos es Aurora PostgreSQL Serverless v2 con `MinCapacity` 0 (pausa automática) y `SecondsUntilAutoPause` de 300 s.
- Versión: Aurora PostgreSQL 16, con versión menor ≥ 16.4. La pausa automática solo existe en versiones menores compatibles: AWS documenta 16.3 o superior, y un hilo de re:Post indica 16.4.

## Cifras (precios de lista de AWS, `sa-east-1`, 2026-10-31)

| Escenario | Coste estimado |
| --- | --- |
| A1 con uso bajo y escala a cero | ≈ US$4/mes |
| A1 sin escala a cero | ≈ US$91/mes |
| Techo del presupuesto | ≈ 79 ACU-h/mes |
| A2: contenedor + PostgreSQL de instancia fija | ≈ US$37–40/mes |

No están verificados los costes de CloudFront, S3 y KMS.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| A2: contenedor + PostgreSQL de instancia fija | ≈ US$37–40/mes, por encima del presupuesto |
| Base de datos local | Descartada en `T-3` (el steering no registra el motivo) |
| Aurora sin escala a cero | ≈ US$91/mes |

## Consecuencias

- La escala a cero es obligatoria. Cualquier conexión abierta impide la pausa (ADR 0004).
- Reanudar tarda unos 15 s, y 30 s o más tras 24 h en pausa. La NFR de latencia (p95 < 500 ms) se mide con la base de datos activa. La primera petición tras una pausa puede tardar hasta ~35 s, así que los clientes usan timeouts ≥ 40 s y muestran «despertando la base de datos».
- Terraform necesita el proveedor de AWS 5.81.0 o superior para `min_capacity = 0`. Con ese valor, `seconds_until_auto_pause` es obligatorio.
- Pendiente: validar el coste con la factura real y la alarma de AWS Budgets al 80 %.

## Referencias

- [Aurora Serverless v2: escala a cero con pausa automática](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
