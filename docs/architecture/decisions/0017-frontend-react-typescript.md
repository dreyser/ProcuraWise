# ADR 0017: Frontend — React + TypeScript

**Estado:** Accepted
**Fecha:** Bloqueado en la especificación aprobada (§27); documentado individualmente el 2026-07-16
**Origen:** Especificación de Producto MVP, §27 (decisión bloqueada, no reabierta en sesiones de planeación)

## Contexto

Esta decisión viene bloqueada desde la especificación de producto aprobada y no fue reabierta durante las sesiones de planeación arquitectónica. Se documenta aquí como ADR individual para dar trazabilidad futura, ya que el plan original (sección M) no le había asignado un número propio.

## Decisión

React + TypeScript como SPA (Vite), servida de forma independiente del backend, consumiendo los tipos y hooks generados desde el contrato OpenAPI (ver [ADR 0007](0007-contratos-openapi-orval.md)).

## Alternativas consideradas

Ninguna evaluada en las sesiones de planeación — la decisión se hereda tal cual de la especificación aprobada §27. Reabrirla requiere un ADR nuevo que la sustituya explícitamente, con aprobación del founder.

## Consecuencias

- Frontend y backend despliegan y escalan de forma independiente.
- La disciplina de contrato (ADR 0007) es obligatoria para mantenerlos sincronizados.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 2.
