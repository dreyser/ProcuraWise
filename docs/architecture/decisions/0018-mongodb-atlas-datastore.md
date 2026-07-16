# ADR 0018: MongoDB Atlas como almacén de datos

**Estado:** Accepted
**Fecha:** Bloqueado en la especificación aprobada (§27); documentado individualmente el 2026-07-16
**Origen:** Especificación de Producto MVP, §27 (decisión bloqueada, no reabierta en sesiones de planeación)

## Contexto

Esta decisión viene bloqueada desde la especificación de producto aprobada y no fue reabierta durante las sesiones de planeación arquitectónica. Se documenta aquí como ADR individual — distinto de [ADR 0002](0002-multi-tenant-mongodb.md) (estrategia multi-tenant sobre Mongo) y [ADR 0015](0015-tier-mongodb-atlas-m0.md) (tier M0) — para dejar trazabilidad de la elección de MongoDB Atlas como el almacén de datos en sí.

## Decisión

MongoDB Atlas es el almacén de datos primario para todos los datos de tenant y de plataforma.

## Alternativas consideradas

Ninguna evaluada en las sesiones de planeación — la decisión se hereda tal cual de la especificación aprobada §27. Reabrirla requiere un ADR nuevo que la sustituya explícitamente, con aprobación del founder.

## Consecuencias

- Modelado orientado a documentos para todos los bounded contexts.
- El aislamiento multi-tenant se implementa en la capa de aplicación/repositorio (ver ADR 0002), no vía separación nativa de tenants a nivel de base de datos.

## Referencias

- [ADR 0002 — Estrategia multi-tenant en MongoDB](0002-multi-tenant-mongodb.md).
- [ADR 0015 — Tier MongoDB Atlas M0](0015-tier-mongodb-atlas-m0.md).
