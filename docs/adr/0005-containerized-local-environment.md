# 0005. Entorno local con Docker y la misma imagen de la API en Lambda

- **Estado:** Aceptado (se implementa en la primera spec de la fase 1)
- **Fecha:** 2026-11-01
- **Decisiones relacionadas:** `T-3` (ADR 0002), `T-10` (ADR 0004), `T-2` (ADR 0001)

## Contexto

El proyecto debe funcionar igual en el equipo del autor, en cualquier otra máquina y en CI antes de llegar a producción. No hay staging: un solo usuario y un presupuesto por debajo de US$20/mes. La API usa Lambda Web Adapter, que permite ejecutar la misma aplicación como servidor web normal fuera de Lambda.

## Decisión

- **Docker Compose** (`compose.yaml` en la raíz) levanta el entorno `local`, y CI usa el mismo entorno. Incluye:
  - la API, construida con su `Dockerfile`;
  - PostgreSQL `postgres:16`, la misma versión mayor que Aurora;
  - la web de Next.js, compilada y servida con nginx, que sustituye a S3 + CloudFront;
  - un emisor JWT de pruebas, que sustituye a Cognito y al autorizador de API Gateway.
- La API se despliega en Lambda como **imagen de contenedor desde Amazon ECR**: la misma imagen que se prueba en local y en CI.
- La autenticación usa un puerto con dos adaptadores, elegidos en `main.py`. En `prod` se leen los claims del autorizador JWT de API Gateway; en `local`, el token se valida contra la JWKS del emisor de pruebas. Una prueba de CI garantiza que la configuración de `prod` no acepta ese emisor.
- El colector **no** se containeriza: corre nativo con uv. Sus pruebas, con el GD50 simulado, corren en CI.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Colector también en contenedor | BLE en un contenedor exige el D-Bus del sistema, red del host y privilegios; solo funciona en Linux y no hay keyring del SO dentro del contenedor |
| Solo PostgreSQL en contenedor | La API y la web dependerían de lo instalado en cada máquina |
| Despliegue en .zip | Lo que se despliega sería un artefacto distinto del probado en local |
| Moto con la API sin autenticación en local | Un modo sin autenticación es un riesgo si llega a producción |
| User pool de Cognito de desarrollo | Exige internet y AWS para desarrollar |

## Consecuencias

- Una máquina nueva solo necesita Docker y uv: el colector corre fuera de Docker.
- Terraform añade un repositorio de ECR en `us-east-1` ([ADR 0011](0011-aws-region-us-east-1-for-cost-optimization.md)) con política de ciclo de vida que conserva solo las últimas imágenes. El almacenamiento en ECR cuesta US$0,10/GB-mes (centavos de dólar al mes para pocas imágenes).
- Una imagen de contenedor puede arrancar en frío más despacio que un .zip. Se mide contra la NFR de latencia.
- El `.dockerignore` excluye `.env`, secretos y datos. Ninguna imagen contiene credenciales.
- Docker **no** verifica lo que solo existe en AWS: el autorizador JWT, la autenticación IAM con Aurora, la pausa y reanudación, la VPC sin NAT, el throttling ni el coste. Lo cubre la prueba de humo tras cada despliegue, descrita en `tech.md`: `/health/ready` firmado con IAM y un 401 sin token, con vuelta al digest anterior si falla.
- Verificado: Lambda Web Adapter entrega el contexto de API Gateway en la cabecera `x-amzn-request-context`. Con HTTP API y autorizador JWT, los claims están en `requestContext.authorizer.jwt.claims`, todos como texto. El adaptador siempre escribe esa cabecera y reemplaza la que envíe el cliente (`HeaderMap::insert`, en su código fuente). Si falta o no trae un `sub`, quien rechaza la petición es la API (criterio 3.2 de `fase-1a`), no el adaptador.

## Referencias

- [Lambda Web Adapter: contexto de la petición y de Lambda](https://aws.github.io/aws-lambda-web-adapter/features/request-context.html)
- [Lambda Web Adapter: código fuente (`src/lib.rs`)](https://github.com/aws/aws-lambda-web-adapter/blob/main/src/lib.rs)
- [Formato 2.0 del evento de HTTP API: `requestContext.authorizer.jwt.claims`](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
