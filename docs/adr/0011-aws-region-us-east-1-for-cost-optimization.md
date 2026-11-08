# 0011. Cambio de región de AWS a us-east-1 para optimización de costes

- **Estado:** Aceptado
- **Fecha:** 2026-11-07
- **Decisiones relacionadas:** `T-3`, `T-10` y `T-11` (`.kiro/steering/tech.md`); actualiza el supuesto regional de [ADR 0002](0002-serverless-compute-and-database.md), [ADR 0004](0004-api-network-without-nat.md), [ADR 0005](0005-containerized-local-environment.md) y [ADR 0008](0008-scoped-deployment-role-and-leak-free-pipeline.md); bloque 5 (`5.2`, `R5.1`) y bloque 8 (`8.1`) de `.kiro/steering/discovery.md`

## Contexto

En el diseño inicial se eligió la región `sa-east-1` (São Paulo, Brasil) por cercanía geográfica a Colombia. Sin embargo, durante el descubrimiento (`.kiro/steering/discovery.md`, bloques 5, 6 y 8) se confirmaron tres hechos que cambian el equilibrio de la decisión:

1. **El coste mensual (`< US$20/mes`) es la dimensión más protegida del proyecto**, por encima del rendimiento y la disponibilidad: el orden explícito de sacrificio del titular es `1. Rendimiento → 2. Disponibilidad → 3. Funcionalidades → 4. Rapidez de entrega → 5. Coste` (`8.1`).
2. **Marco legal personal (`5.1`, `5.2`):** MonitorGlucosa es una plataforma estrictamente personal, monousuario y sin comercialización ni terceros, amparada en la excepción de ámbito personal de la Ley 1581/2012 (art. 2 lit. a), sin obligación regulatoria de residencia geográfica en Sudamérica.
3. **Diferencia de precios públicos en AWS:** `sa-east-1` tiene tarifas significativamente superiores a `us-east-1` (N. Virginia) tanto en cómputo por ACU-hora de Aurora Serverless v2 como en almacenamiento, transferencia y servicios auxiliares, reduciendo el margen disponible dentro del presupuesto de US$20/mes (con alarma al 80 % = US$16/mes). Además, la infraestructura aún no se ha desplegado en AWS (`fase-1a` va por la tarea 10 de 33, antes del bootstrap de cuenta), por lo que el cambio de región tiene coste de migración cero hoy.

## Criterios

En el orden de las prioridades del descubrimiento (bloque 8 de `.kiro/steering/discovery.md`):

1. **Coste mensual de operación (`< US$20/mes`, prioridad #5 más protegida):** minimizar el precio unitario por ACU-hora, almacenamiento y peticiones para sostener el sistema indefinidamente con presupuesto personal.
2. **Disponibilidad de servicios y soporte en AWS:** contar con el catálogo completo de características y menor riesgo de limitaciones regionales en Aurora Serverless v2, Cognito y Lambda.
3. **Latencia de red (prioridad #1, la primera que se sacrifica):** con un único usuario, sincronización BLE por lotes y sesiones web breves, añadir ~40–60 ms de RTT entre Colombia y `us-east-1` frente a `sa-east-1` es imperceptible frente al objetivo de `p95 < 500 ms` con base de datos activa.

## Matriz de decisión

| Opción | Coste de lista en AWS (presupuesto `< US$20/mes`) | Catálogo de servicios y soporte | Latencia desde Colombia y cumplimiento | Conclusión |
| --- | --- | --- | --- | --- |
| **`us-east-1` (N. Virginia, EE. UU.)** | Aurora Serverless v2: **US$0,12/ACU-h** y **US$0,10/GB-mes**; con `MinCapacity = 0` y uso personal esporádico + Secrets Manager (**US$0,40/mes** por el secreto maestro de RDS) + claves KMS gestionadas por AWS (**US$0/mes** fijo) + S3/ECR/CloudWatch: **≈ US$2–4/mes** (frente a ~US$43,80/mes si no pausara a 0). Techo del presupuesto (~US$18 disponibles para ACU): **≈ 150 ACU-h/mes** | Región principal de AWS con disponibilidad inmediata de versiones menores de Aurora ≥ 16.4 y Cognito Essentials; simplifica `aws:RequestedRegion = us-east-1` ([ADR 0008](0008-scoped-deployment-role-and-leak-free-pipeline.md)) | RTT ~60–90 ms desde Colombia (cumple `p95 < 500 ms`); permitido para uso personal (`5.2`) | **Elegida** |
| **`sa-east-1` (São Paulo, Brasil)** | Aurora Serverless v2: **US$0,25/ACU-h** (+108 %) y **US$0,19/GB-mes** (+90 %); sin pausa costaría ~US$91,25/mes y el techo de presupuesto permitía solo ~79 ACU-h/mes | Menor disponibilidad de lanzamientos y precios más altos en endpoints y servicios | RTT ~90–120 ms desde Colombia (ruteo submarino habitual vía EE. UU.); sin ventaja legal real para uso personal | Descartada por mayor coste unitario |

## Decisión

1. **Región única en la nube:** toda la infraestructura y los datos en AWS del MVP (API Gateway, Lambda, Aurora PostgreSQL Serverless v2, S3 del sitio web e informes PDF, KMS, Cognito, CloudWatch, Parameter Store y Secrets Manager) se despliegan exclusivamente en **`us-east-1` (N. Virginia, Estados Unidos)**.
2. **Conservación íntegra de la arquitectura de ahorro (`R5.1a`):** el ahorro de precios unitarios de `us-east-1` se destina exclusivamente a reducir la factura mensual y aumentar el margen bajo los US$16/mes; **no** se utiliza para añadir componentes de coste fijo. Se mantienen sin cambios:
   - API en Lambda y Aurora PostgreSQL Serverless v2 con `MinCapacity = 0` y auto-pausa tras 300 s ([ADR 0002](0002-serverless-compute-and-database.md)), ahorrando ~US$40–42/mes en `us-east-1` frente a mantener 0,5 ACU continuos (~US$43,80/mes).
   - Lambda en VPC privada **sin NAT Gateway** (que en `us-east-1` cuesta US$0,045/h ≈ US$32,85/mes fijos), con endpoint gateway gratuito para S3 y conexión TLS + IAM a Aurora ([ADR 0004](0004-api-network-without-nat.md)).
   - Cifrado en reposo con **claves KMS gestionadas por AWS** (`aws/rds`, `aws/s3`, `aws/lambda`, `aws/secretsmanager`) sin coste fijo mensual de US$1/clave CMK; el único cargo fijo mensual es el secreto maestro de Aurora gestionado por RDS en Secrets Manager (US$0,40/mes, [ADR 0007](0007-idempotent-sql-bootstrap-through-rds-data-api.md)).
   - Dos alarmas en AWS Budgets: al **80 % (US$16/mes)** y al **100 % (US$20/mes)**, con tope absoluto de desviación puntual de **US$30/mes** (`R6.2`).
3. **Sincronización previa a continuar `fase-1a` (`R5.1b`):** antes de retomar la tarea 11 de `.kiro/specs/fase-1a-infraestructura-y-auth/` y antes de ejecutar el bootstrap en AWS, se sincronizará la spec con `/spec-sync` para sustituir `sa-east-1` por `us-east-1`.

## Consecuencias

- Se reduce el coste mensual estimado de operación en AWS manteniendo exactamente la misma topología sin servidores y sin costes fijos por hora.
- Se actualizan `.kiro/steering/product.md`, `.kiro/steering/tech.md`, `.kiro/steering/structure.md`, `docs/architecture/diagrams.py` y, mediante `/spec-sync`, la spec activa `fase-1a-infraestructura-y-auth`.
- **Qué haría cambiar esta decisión:** que el sistema pasara a comercializarse o a prestar servicio a terceros en una jurisdicción que exija contractual o legalmente residencia de datos en otro territorio (`P-2`).

## Referencias

- [Precios de Amazon Aurora Serverless v2](https://aws.amazon.com/rds/aurora/pricing/)
- [Precios de AWS Lambda](https://aws.amazon.com/lambda/pricing/)
- ADR 0002: [API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero](0002-serverless-compute-and-database.md)
- ADR 0004: [Acceso de la API a Aurora sin NAT Gateway](0004-api-network-without-nat.md)
