<!-- Título del PR en Conventional Commits (p. ej. feat(collector): sincronizar lecturas). El merge es por rebase:
     cada commit de la rama llega a main con su `Refs: <spec>#<tarea>`. /kiro:spec-pr rellena esta plantilla desde la
     spec y la matriz de trazabilidad. Repositorio público: nada de secretos ni datos reales. -->

## Resumen

<qué cambia y por qué, en 2 a 4 líneas>

## Spec

- Spec: `.kiro/specs/<spec>/` · tareas: <N, N.M…>
- Requisitos y criterios cubiertos: <IDs>
- Decisiones y ADR: <D1, ADR NNNN, T-n o —>

## Trazabilidad

<extracto de `kspec trace --commits <spec>`: criterio → tareas → commits → estado>

## Verificación

- [ ] Pruebas en verde: <comando de tech.md>
- [ ] Lint, formato y tipos sin errores
- [ ] `kspec lint <spec>` y `kspec trace check` sin errores
- [ ] `kspec diagrams check` en verde y ADR registrados (si cambia la arquitectura)
- [ ] `/spec-converge`: «Convergencia: completa»

## Seguridad

- [ ] Sin secretos, `.env` ni datos personales en el diff, los logs ni este PR
- [ ] Entradas externas validadas; permisos mínimos; infraestructura como código (si aplica)

## Cómo probarlo

<pasos para comprobar el cambio>
