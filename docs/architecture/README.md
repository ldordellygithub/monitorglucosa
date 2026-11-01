# Diagramas de arquitectura · monitorglucosa

> Generado por `docs/architecture/diagrams.py`. No edites este archivo ni el `.drawio` a mano: cambia el modelo y regenera.

| Vista | Pregunta que responde | Imagen |
| --- | --- | --- |
| 1 · Contexto del sistema · C4 nivel 1 | ¿Quién usa el sistema y con qué se relaciona? | [01-contexto.svg](svg/01-contexto.svg) |
| 2 · Contenedores · C4 nivel 2 | ¿Qué piezas hay y cómo se comunican? | [02-contenedores.svg](svg/02-contenedores.svg) |
| 3 · Red y despliegue en AWS | ¿Dónde corre cada pieza (VPC, subredes, endpoints, IAM)? | [03-red-y-despliegue.svg](svg/03-red-y-despliegue.svg) |
| 4 · Componentes · C4 nivel 3 | ¿Cómo están organizados por dentro el backend y el colector? | [04-componentes.svg](svg/04-componentes.svg) |
| 5 · Secuencia · sincronización de lecturas (fase 1) | ¿En qué orden se sincronizan las lecturas, con reintentos e idempotencia? | [05-secuencia-sincronizacion.svg](svg/05-secuencia-sincronizacion.svg) |
| 6 · Secuencia · autenticación del colector (T-7) | ¿Cómo obtiene y renueva sus tokens el colector? | [06-secuencia-autenticacion.svg](svg/06-secuencia-autenticacion.svg) |
| 7 · Modelo conceptual de datos | ¿Qué entidades hay y qué garantiza cada una? | [07-modelo-conceptual.svg](svg/07-modelo-conceptual.svg) |
| 8 · Flujo de datos, límites de confianza y STRIDE | ¿Por dónde viajan los datos de salud y cómo se protegen en cada límite? | [08-flujo-de-datos.svg](svg/08-flujo-de-datos.svg) |
| 9 · Ciclo de vida de los datos de salud | ¿Dónde vive cada dato, cuánto se conserva y cómo se borra? | [09-ciclo-de-vida-datos.svg](svg/09-ciclo-de-vida-datos.svg) |
| 10 · CI/CD · de un cambio a producción | ¿Cómo llega un cambio a producción? | [10-ci-cd.svg](svg/10-ci-cd.svg) |

## Decisiones de arquitectura (ADR)

| ADR | Decisión | Estado |
| --- | --- | --- |
| [0001](../adr/0001-ble-collector-location.md) | Colector BLE local, separado del backend | Aceptado |
| [0002](../adr/0002-serverless-compute-and-database.md) | API en Lambda y Aurora PostgreSQL Serverless v2 con escala a cero | Aceptado |
| [0003](../adr/0003-collector-authentication.md) | Autenticación del colector con refresh token de Cognito | Aceptado |
| [0004](../adr/0004-api-network-without-nat.md) | Acceso de la API a Aurora sin NAT Gateway | Aceptado |
| [0005](../adr/0005-containerized-local-environment.md) | Entorno local con Docker y la misma imagen de la API en Lambda | Aceptado |

## Steering

Contexto, decisiones abiertas y restricciones: [product.md](../../.kiro/steering/product.md) · [tech.md](../../.kiro/steering/tech.md) · [structure.md](../../.kiro/steering/structure.md).

## Regenerar

```bash
python3 docs/architecture/diagrams.py        # modelo -> arquitectura-monitorglucosa.drawio y README.md
kspec diagrams export                        # arquitectura-monitorglucosa.drawio -> svg/ (necesita draw.io Desktop)
kspec diagrams check                         # modelo, geometría y SVG al día (también en CI)
```

## Convenciones

- Colores C4: persona en azul oscuro, contenedor propio en azul, sistema externo en gris violeta y dispositivo en gris.
- Lo *Propuesto* y las fases futuras van en gris discontinuo; las decisiones abiertas, en notas rojas con su ID.
- Las vistas de infraestructura usan los iconos oficiales de AWS (biblioteca `aws4` de draw.io).
- Los nombres de clases de las vistas de componentes son orientativos: los fija cada spec.
- Si un cambio afecta a un componente o a un flujo, actualiza el modelo y regenera en el mismo PR.
