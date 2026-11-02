# 0009. Reanudación de Aurora con un 503 reintentable dentro del límite de 30 s

- **Estado:** Aceptado
- **Fecha:** 2026-11-02
- **Decisiones relacionadas:** spec `fase-1a-infraestructura-y-auth` (D7, criterios 2.2 y 5.4, NFR-2); `T-3` (ADR 0002) y `T-10` (ADR 0004); sustituye la frase de latencia de `tech.md · Requisitos no funcionales` (se aplica en la tarea 23)

## Contexto

Aurora Serverless v2 con `MinCapacity` 0 se pausa tras 300 s sin conexiones (`T-3`) y se reanuda cuando llega una conexión. `tech.md` decía que «la primera petición puede tardar hasta ~35 s», pero API Gateway corta cualquier integración a los 30 s, así que ninguna petición individual puede esperar tanto.

Datos verificados en la documentación oficial de AWS (2026-11-02):

- **HTTP API:** el tiempo máximo de integración es de 30 s y no se puede ampliar.
- **Reanudación:** tarda unos 15 s; si la instancia lleva más de 24 h en pausa, 30 s o más. AWS recomienda un timeout de conexión mayor que 15 s (30 s o más tras inactividad de más de un día) y reintentar la conexión.
- **Qué la dispara:** la conexión se establece cuando la instancia termina de reanudar, y un intento de conexión con credenciales inválidas también la reanuda.
- **Concurrencia:** si una instancia en pausa recibe muchas conexiones antes de terminar de reanudar, algunas sesiones pueden no conectar; AWS recomienda reintentos (por ejemplo, tres).
- **Qué impide la pausa:** cualquier conexión abierta por el usuario; las conexiones administrativas de comprobación de salud no cuentan.

No verificado: el código exacto que devuelve HTTP API cuando la integración supera el límite (AWS no lo documenta; la comunidad observa un 503). La verificación manual registra el observado (`manual-checks.md`).

## Decisión

- La API abre la conexión a Aurora con un `connect_timeout` de 20 s (`DATABASE_CONNECT_TIMEOUT_S`, entre 1 y 25, 20 por defecto). Deja unos 10 s de margen frente al límite de 30 s para el arranque en frío, la firma del token IAM y el TLS. Es menos que los 30 s o más que AWS recomienda tras más de un día en pausa: el límite del gateway impide darle más, y el reintento del cliente compensa la diferencia.
- Si la conexión se agota o se rechaza, la API responde **503 `DATABASE_UNAVAILABLE`** con el cuerpo de error uniforme y la cabecera `Retry-After: 5`. La Lambda tiene un timeout de 30 s, igual que el límite del gateway.
- `GET /health` nunca abre una conexión (2.1). `GET /health/ready` la abre y responde 200 o 503 (2.2).
- Cada petición abre y cierra su propia conexión (5.4), así un intento fallido no deja una sesión que impida la pausa.
- **Contrato de reintento para los clientes:** ante un 503 de la API, esperar lo que indique `Retry-After` y reintentar; ante un 5xx de API Gateway porque la Lambda superó los 30 s (llega sin esa cabecera), esperar 5 s y reintentar. En total, hasta 60 s (NFR-2: `/health/ready` responde 200 en ≤ 60 s sumando los reintentos, y cada petición individual termina antes de 30 s). La prueba de humo de cada despliegue (7.5) aplica el mismo contrato con un margen mayor, hasta 120 s (`scripts/smoke_test.py`, D5).
- La frase de `tech.md` se sustituye por este contrato (tarea 23, con la aprobación del propietario y `kspec steering-sync`).

**Aritmética del peor caso** (estimación a partir de las cifras de AWS; no medida en esta cuenta): tras más de 24 h en pausa, el primer intento agota sus 20 s y recibe un 503; el cliente espera 5 s y reintenta hacia los 25 s; ese intento espera a que termine la reanudación, que AWS sitúa en 30 s o más, y conecta antes de los 45 s. Cabe en los 60 s solo si la reanudación dura unos 45 s o menos: «30 s o más» no tiene tope documentado. Esto supone que abandonar el primer intento no cancela la reanudación: AWS documenta que un intento de conexión la inicia aun fallando, pero no que sobreviva a un cliente que se desconecta, así que se confirma midiendo.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Una REST API con un timeout de integración ampliado | Vuelve a abrir `T-10`; el ADR 0004 ya eligió HTTP API |
| Mantener Aurora despierta con una capacidad mínima mayor que 0 | ≈ US$91/mes, contradice `T-3` |

## Consecuencias

- El colector y la web heredan este contrato: tratan el 503 como «despertando la base de datos» y reintentan en vez de fallar. Cada spec lo implementa en su cliente.
- Si Aurora tarda más de ~60 s en reanudar, el cliente interactivo falla; la prueba de humo tolera hasta 120 s. El tiempo real de reanudación tras más de 24 h se mide y se anota en `manual-checks.md` (NFR-2).
- Todo fallo al conectar con Aurora responde 503, también uno de autenticación (por ejemplo, falta `rds-db:connect`). Se consideró separar las causas y el 2026-11-02 se decidió no hacerlo, por simplicidad. AWS indica no reintentar los fallos de autenticación, así que ese error se reintentaría en vano: los clientes tardan hasta 60 s en darse por vencidos y la prueba de humo del despliegue, 120 s. La respuesta no distingue el caso de la reanudación; la señal es que la prueba de humo falle.
- Que API Gateway entregue la cabecera `Retry-After` de la API lo ejercita la prueba de humo, que la respeta.
- Riesgo de ruido en las alarmas: AWS define la métrica `5xx` de HTTP API solo como «errores del lado del servidor» y no precisa si cuenta los 503 que devuelve la propia Lambda. Si los cuenta, un 503 de reanudación tras una pausa larga avisaría por correo sin ser un fallo. Se observa al probar la alarma (8.4) y, si ocurre, se ajusta la alarma en la spec de operación.
- Se prueba con:
  - una prueba unitaria de `CheckReadiness` con un `DatabaseProbe` falso que agota el tiempo;
  - pruebas de integración contra PostgreSQL real (`/health` responde 200 con la base de datos inaccesible; `/health/ready` responde 200 o 503);
  - Schemathesis con la base de datos inaccesible (Property 8);
  - la medición manual de NFR-2 en `prod`.

## Referencias

- [Cuotas de HTTP API en API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html)
- [Métricas de CloudWatch para HTTP API](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html)
- [Aurora Serverless v2: pausa y reanudación automáticas](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
- [RFC 9110: cabecera `Retry-After` con el estado 503](https://www.rfc-editor.org/rfc/rfc9110)
- ADR 0002: [API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero](0002-serverless-compute-and-database.md)
- ADR 0004: [Acceso de la API a Aurora sin NAT Gateway](0004-api-network-without-nat.md)
