# 0003. Autenticación del colector con refresh token de Cognito

- **Estado:** Aceptado (callback `http://localhost` pendiente de validar en la spec de fase 1)
- **Fecha:** registrado el 2026-11-01; la decisión ya figuraba en `tech.md` como `T-7`
- **Decisión relacionada:** `T-7` (y `T-4` para la web)

## Contexto

El colector corre en el equipo del usuario y debe llamar a la API sin credenciales de AWS ni secretos de larga duración en disco. El access token de Cognito dura 60 minutos por defecto. Hace falta renovarlo sin pedir la contraseña en cada sincronización.

## Decisión

1. Primer inicio de sesión: autorización con código y PKCE (S256) en Cognito.
2. El refresh token se guarda en el almacén seguro del sistema operativo, nunca en el repositorio ni en un archivo de configuración.
3. Antes de cada sesión BLE, el colector lo canjea por un access token con `GetTokensFromRefreshToken`. `REFRESH_TOKEN_AUTH` no admite rotación.
4. La rotación de refresh tokens está activada. Exige el plan **Essentials** (o Plus) de Cognito, porque no existe en Lite. `RetryGracePeriodSeconds` se fija explícitamente en Terraform: si no se fija, vale 0.
5. El refresh token dura **30 días**. La rotación no extiende ese plazo: el token nuevo caduca cuando caducaba el original, así que el colector repite el inicio de sesión con PKCE cada 30 días.
6. Revocación: `RevokeToken` al cerrar sesión. Si se pierde el equipo, `AdminUserGlobalSignOut` con credenciales del administrador, nunca del colector.
7. La web usa MFA TOTP obligatorio, sin SMS. Cognito no da códigos de respaldo: si se pierde el teléfono, el MFA se resetea con credenciales de administrador.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Secreto local con client credentials | Secreto de larga duración en disco |
| Token estático local | Sin caducidad ni revocación (`T-4`) |
| Device authorization grant | No está verificado en Cognito |

## Consecuencias

- Un login en el navegador al mes. La ventana máxima de un token robado sin detectar es de 30 días, y se cierra antes con la revocación.
- El plan Essentials es obligatorio. Su coste con un solo usuario está por verificar.
- Si AWS no acepta el callback `http://localhost` en producción, se usa un esquema de redirección propio (spec de fase 1).

## Referencias

- [Cognito: refresh tokens y rotación](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)
- [Anuncio de la rotación de refresh tokens (2025-04-22)](https://aws.amazon.com/about-aws/whats-new/2025/04/amazon-cognito-refresh-token-rotation/)
