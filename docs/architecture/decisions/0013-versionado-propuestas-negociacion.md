# ADR 0013: Versionado de propuestas para ronda de negociación

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

El producto necesita una ronda final de negociación (Ronda 0 inicial inmutable + Ronda 1 opcional de negociación/BAFO) sin perder el historial de qué cambió, y sin invalidar incorrectamente evaluaciones ya realizadas.

## Decisión

Cada `ProposalAnswer` de una nueva versión registra `status: inherited | modified | removed` + `source_proposal_version`. Un `Score` pertenece a una versión específica de la propuesta: modificar una respuesta invalida su score; cambiar una rúbrica o requerimiento invalida todos los scores afectados por igual. El TCO se recalcula completo por versión — nunca se mezclan costos de versiones distintas. El comparativo final siempre usa la última propuesta válida de cada proveedor.

## Alternativas consideradas

- **Mutar la propuesta en el lugar durante la ronda de negociación**: descartado — viola el principio de inmutabilidad por versión (snapshot al enviar propuesta) y pierde el rastro de auditoría de qué cambió.
- **Exigir reenvío completo sin herencia de respuestas**: descartado — fricción excesiva para el proveedor y ninguna visibilidad de diferencias para los evaluadores.

## Consecuencias

- Almacenamiento adicional por cada versión de propuesta (aceptado, dado el volumen objetivo del MVP: 500 evaluaciones).
- La lógica de invalidación de scores debe probarse explícitamente (ver criterios de aceptación de la Fase 21 en `backlog.md`).
- No invitados a la ronda de negociación conservan su propuesta inicial; invitados sin respuesta conservan la anterior marcada como "no actualizada" salvo descalificación configurada.

## Referencias

- Backlog, Fase 21.
- [`docs/architecture/architecture.md`](../architecture.md), sección 6.
