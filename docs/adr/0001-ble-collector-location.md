# 0001. Colector BLE local, separado del backend

- **Estado:** Aceptado
- **Fecha:** registrado el 2026-11-01; la decisión ya figuraba en `tech.md` como `T-2`
- **Decisión relacionada:** `T-2`

## Contexto

El glucómetro GlucoQuick GD50 entrega sus lecturas por Bluetooth Low Energy (perfil Glucose, `0x1808`). La API corre en AWS (`T-3`), y un servidor en la nube no puede hablar BLE con un dispositivo que está junto al usuario. Hace falta un componente cercano al medidor que lea las lecturas y las envíe a la API.

## Decisión

Un colector en Python con `bleak` se ejecuta en el equipo local del usuario (Ubuntu, BlueZ). Lee las lecturas almacenadas por RACP, las normaliza y las envía a `/api/v1` por HTTPS con un access token de Cognito (`T-7`). El colector no importa código del backend: el único contrato es el esquema OpenAPI.

## Alternativas descartadas

| Alternativa | Motivo del descarte |
| --- | --- |
| Web Bluetooth desde el navegador | Solo funciona en Chromium; exige HTTPS y un gesto del usuario; no funciona en Firefox ni en Safari |
| Lectura BLE dentro del backend | Imposible: el backend corre en AWS, lejos del dispositivo |

## Consecuencias

- El backend no depende de BLE y se prueba sin hardware: el GD50 se simula con un adaptador falso.
- La sincronización exige tener el laptop y el medidor cerca. Lo mitiga el registro manual de respaldo (fase 1).
- El colector es un cliente más de la API, sin reglas de negocio. Guarda localmente solo el hash de las claves ya enviadas, nunca valores de salud.
- El equipo del colector guarda un refresh token: su robo o pérdida se gestiona según `T-7` (ADR 0003).
