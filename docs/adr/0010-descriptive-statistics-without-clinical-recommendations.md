# 0010. Estadística descriptiva, inventario y patrones objetivos sin recomendaciones clínicas

- **Estado:** Aceptado
- **Fecha:** 2026-11-07
- **Decisiones relacionadas:** `P-5` y `P-2` (`.kiro/steering/product.md`); bloque 1 (`R1.2`, `R1.3`, `Q-l`) y bloque 2 (`R2.4`, opción `a1+`) de `.kiro/steering/discovery.md`

## Contexto

La redacción original de `P-5` en `.kiro/steering/product.md` establecía que las dosis anotadas se mostraban «tal cual, sin cálculos derivados». Durante el descubrimiento (`.kiro/steering/discovery.md`, bloques 1 y 2), el titular definió tres necesidades para preparar el 100 % de sus consultas médicas con sus cuatro especialistas (endocrinólogo, oftalmólogo, médico general y odontólogo):

1. Incluir en el informe PDF y en las vistas analíticas **estadística descriptiva calculada exclusivamente sobre sus propios registros** (`R2.4`, opción `a1+`): número de dosis del período, días con registro (con desglose objetivo por número de aplicaciones diarias: `0`, `1`, `2`, `3+`, sin requerir ni almacenar una pauta prescrita), días sin registro, intervalo entre dosis y suma de unidades aplicadas, además de promedios, mínimos, máximos, tiempo en rango y distribución por horarios de glucemia.
2. Mantener un **inventario de insulina** acoplado al registro de dosis (`R1.3`, `Q-o`) que descuente automáticamente las unidades aplicadas, recalcule el saldo al editar o borrar una dosis (`R3.2`) y muestre estimaciones informativas de saldo y duración.
3. Detectar **patrones objetivos** sobre las lecturas sincronizadas (`Q-l`): recurrencia de lecturas bajo o sobre los umbrales configurados por el titular en seis bloques fijos de 4 horas, y cambio de promedio semanal mayor al 15 % relativo y mayor a 15 mg/dL absolutos.

Al mismo tiempo, el proyecto debe mantenerse estrictamente fuera de la categoría de software de soporte a decisiones médicas o dispositivo médico regulado ante INVIMA (`P-2`), y proteger a un usuario único que es a la vez su único probador.

## Criterios

En el orden de los intocables y prioridades del descubrimiento (bloque 8 de `.kiro/steering/discovery.md`):

1. **Frontera clínica y regulatoria (`P-5`, `P-2`, intocable #4):** ninguna funcionalidad puede emitir diagnósticos, prescribir, recomendar ajustes de dosis ni evaluar la eficacia de un tratamiento.
2. **Integridad, exactitud y trazabilidad de los datos (intocables #1 y #5):** toda cifra mostrada en la web o en el informe PDF debe ser una función determinista, verificable por pruebas automatizadas y reproducible a partir de los registros almacenados.
3. **Utilidad práctica en consulta médica (métrica principal #1):** entregar a los cuatro especialistas un informe histórico consolidado y autoexplicativo sin requerir cálculo manual fuera del sistema.

## Matriz de decisión

| Opción | Frontera `P-5` y riesgo INVIMA (`P-2`) | Integridad y verificabilidad | Utilidad en consulta médica | Conclusión |
| --- | --- | --- | --- | --- |
| **Opción `a1+` (enmienda estrecha de `P-5`)**: hechos + estadística descriptiva sobre registros propios + saldo de inventario + patrones sobre umbrales configurados | Cumple: expone hechos y agregados matemáticos objetivos con descargo visible; el juicio clínico lo realiza el médico | 100 % verificable con pruebas unitarias deterministas sobre datos sintéticos | Alta: entrega totales, intervalos, promedios y distribución temporal listos para consulta | **Elegida** |
| **Opción `a1` estricta (redacción previa)**: mostrar dosis y lecturas solo tal cual, sin ningún agregado ni saldo | Cumple la frontera regulatoria | Verificable (solo listado) | Insuficiente: obliga al titular y al médico a contar dosis, días e inventario a mano | Descartada por baja utilidad |
| **Opción `b` (adherencia, correlación causal dosis-glucemia o sugerencia de dosis)** | Incumple `P-5` y activa riesgo regulatorio de software médico (`P-2`) y riesgo vital de hipoglucemia severa | No verificable: con `n = 1` y confundidores no medidos (comidas, ejercicio, estrés) no existe función computable ni oráculo de prueba válido | Peligrosa: puede inducir a decisiones terapéuticas sobre conclusiones estadísticamente inválidas | Descartada por seguridad e inverificabilidad |

## Decisión

Se enmienda `P-5` en `.kiro/steering/product.md` bajo las siguientes reglas verificables:

1. **Permitido (estadística descriptiva y agregados objetivos):**
   - Sobre aplicaciones de insulina (`a1+`): conteo de dosis en el período, días con al menos un registro y distribución de días por cantidad de registros (`0`, `1`, `2`, `3+`, sin comparar contra pauta prescrita), días sin registro, intervalo temporal entre aplicaciones y suma total de unidades registradas.
   - Sobre inventario de insulina: cálculo de saldo actual (compras y ajustes manuales menos dosis registradas) y estimación informativa de duración basada en el ritmo histórico de registro, más avisos objetivos cuando el saldo cruza el umbral configurado por el usuario.
   - Sobre lecturas de glucosa: promedio, mínimo, máximo, desviación/variabilidad, porcentaje de lecturas dentro y fuera de los umbrales configurados por el titular, distribución en seis bloques fijos de 4 horas (`00:00–03:59`, `04:00–07:59`, `08:00–11:59`, `12:00–15:59`, `16:00–19:59`, `20:00–23:59`) en la zona horaria activa del usuario, comparación entre dos periodos y las tres reglas del motor de patrones (`Q-l`).
2. **Prohibido en todas las fases (incluida la fase 5):**
   - Emitir diagnósticos, sugerir dosis de insulina o carbohidratos, o recomendar cambios en la pauta médica.
   - Calcular porcentajes de «adherencia terapéutica» o «cumplimiento del tratamiento» contra una prescripción médica.
   - Declarar causalidad entre una dosis de insulina y una lectura posterior o evaluar la «efectividad» del tratamiento.
   - Usar constantes clínicas codificadas como verdad médica del sistema: todo umbral es configurable por el usuario y sus valores iniciales provienen de una guía clínica citada con descargo visible (`P-2`, `D-2`).
3. **Separación estricta de dominios (`Q-r`):** la categoría «medicación» de las anotaciones se reserva exclusivamente para medicamentos distintos de la insulina; toda aplicación de insulina se registra por su módulo específico para no distorsionar los agregados descriptivos ni el inventario.

## Consecuencias

- El informe PDF, las exportaciones y el módulo de análisis pueden calcular y mostrar agregados descriptivos reproducibles y cubiertos por pruebas unitarias y de propiedades.
- Toda pantalla de análisis, alerta e informe PDF debe incluir el descargo visible de que la información es descriptiva y no sustituye el criterio del profesional de salud.
- **Qué haría cambiar esta decisión:** si el proyecto dejara de ser personal y monousuario o se pretendiera incorporar soporte a decisiones clínicas, lo cual exigiría previamente asesoría regulatoria formal ante INVIMA (`P-2`), validación clínica independiente y un nuevo ADR.

## Referencias

- `.kiro/steering/discovery.md`: bloque 1 (`R1.2`, `R1.3`, `Q-l`, `Q-o`) y bloque 2 (`R2.2`, `R2.4`, `Q-r`)
- `.kiro/steering/product.md`: principios de producto y decisiones abiertas (`P-2`, `P-5`)
