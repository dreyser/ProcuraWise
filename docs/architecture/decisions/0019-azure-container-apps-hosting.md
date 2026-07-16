# ADR 0019: Hosting — Azure Container Apps

**Estado:** Accepted
**Fecha:** Bloqueado en la especificación aprobada (§27); documentado individualmente el 2026-07-16
**Origen:** Especificación de Producto MVP, §27 (decisión bloqueada, no reabierta en sesiones de planeación)

## Contexto

Esta decisión viene bloqueada desde la especificación de producto aprobada y no fue reabierta durante las sesiones de planeación arquitectónica. Se documenta aquí como ADR individual — distinto de [ADR 0004](0004-bicep-vs-terraform.md) (Bicep como IaC) — para dejar trazabilidad de la elección de la plataforma de cómputo/hosting en sí.

## Decisión

Azure Container Apps aloja los contenedores de API y worker en staging y producción.

## Alternativas consideradas

Ninguna evaluada en las sesiones de planeación — la decisión se hereda tal cual de la especificación aprobada §27. Reabrirla requiere un ADR nuevo que la sustituya explícitamente, con aprobación del founder.

## Consecuencias

- Se requiere despliegue containerizado (`Dockerfile.api`, `Dockerfile.worker`) a partir de la Fase 27.
- La infraestructura real solo se aprovisiona en esa fase; todo el desarrollo anterior (Bloques 0-5) corre 100% local vía Docker Compose.

## Referencias

- [ADR 0004 — Bicep sobre Terraform](0004-bicep-vs-terraform.md).
- [`docs/operations/deployment.md`](../../operations/deployment.md).
