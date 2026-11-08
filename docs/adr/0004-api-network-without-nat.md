# 0004. Acceso de la API a Aurora sin NAT Gateway

- **Estado:** Aceptado (región actualizada de `sa-east-1` a `us-east-1` por [ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md), manteniendo la arquitectura sin NAT Gateway)
- **Fecha:** 2026-11-01 (actualizado el 2026-11-07)
- **Decisiones relacionadas:** `T-10` y `T-11` (complementa `T-3`, ADR 0002 y [ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md))

## Contexto

Aurora vive en subredes privadas de la VPC. Si Lambda entra en la VPC para conectarse por TCP, pierde la salida a internet. Para validar el JWT de Cognito (claves JWKS) o llamar a otros servicios haría falta un NAT Gateway, cuyo precio oficial en `us-east-1` es US$0,045/h (≈ US$32,85/mes fijos antes de tráfico; ≈ US$68/mes en `sa-east-1`). Eso supera por sí solo el presupuesto total de US$20/mes. Además, AWS documenta que las sesiones abiertas impiden la pausa automática de Aurora, y un contenedor Lambda congelado conserva su conexión.

## Decisión

- API Gateway HTTP API va delante de Lambda, con un autorizador JWT de Cognito que valida firma, emisor, `aud` o `client_id` y expiración. Lambda no necesita consultar JWKS.
- Lambda va en la VPC, sin NAT. Se conecta a Aurora por TLS con autenticación IAM: el token se firma localmente, sin llamar a ninguna API.
- Cada petición abre y cierra su propia conexión. No hay pool persistente ni RDS Proxy, que AWS recomienda quitar en clústeres que deben pausarse.
- S3 se usa a través de un endpoint gateway de VPC.
- Throttling global de API Gateway: 10 peticiones/s con ráfagas de 20.
- **Configuración (`T-11`):** sin NAT, la Lambda no alcanza Parameter Store ni Secrets Manager en ejecución. Terraform lee la configuración en el despliegue y la inyecta como variables de entorno, cifradas en reposo con la clave KMS de AWS. Esas variables nunca contienen secretos, porque son visibles con `lambda:GetFunctionConfiguration`.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| NAT Gateway | US$0,045/h ≈ US$32,85/mes fijos en `us-east-1` (≈ US$68/mes en `sa-east-1`), supera el presupuesto de US$20/mes |
| Lambda fuera de la VPC + RDS Data API | Disponible en `us-east-1` para Aurora PostgreSQL ≥ 13.11, 14.8, 15.3 y 16.1, pero acopla los repositorios a una API de AWS, la ruta no se prueba con PostgreSQL real y no está verificado cómo responde con la base de datos pausada |
| RDS Proxy | Impide la pausa automática y tiene coste propio |
| Lambda Function URL | Sin autorizador JWT ni throttling gestionado |
| Endpoint de interfaz de SSM para leer la configuración en ejecución | US$0,01/h por AZ en `us-east-1` (≈ US$14,60/mes con 2 AZs), consume más del 70 % del presupuesto mensual |

## Consecuencias

- Abrir una conexión con TLS e IAM en cada petición añade latencia (no medida). Se valida contra la NFR de p95 < 500 ms con la base de datos activa.
- La fase 4 (WhatsApp, proveedor de AI) necesitará salida a internet. Esa spec define cómo, sin NAT permanente.
- El límite de peticiones es global, no por cliente: con un solo usuario protege igual frente a un bucle del colector. Un límite por cliente exigiría WAF (≈ US$5/mes o más).

## Referencias

- [Aurora Serverless v2: escala a cero con pausa automática](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
- [Regiones y motores del RDS Data API](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.Data_API.html)
- [Precios de Amazon VPC (NAT Gateway)](https://aws.amazon.com/vpc/pricing/)
