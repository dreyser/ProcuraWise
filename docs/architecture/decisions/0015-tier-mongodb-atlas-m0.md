# ADR 0015: Tier de MongoDB Atlas — M0 (free) para todo el MVP

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

El MVP no tiene ingresos aún. Se busca minimizar el costo de infraestructura mientras se valida el producto con clientes piloto, dentro del techo de NFR-003 (50 usuarios concurrentes, global de la plataforma).

## Decisión

MongoDB Atlas tier **M0 (free)** para todo el MVP, con IP allowlist. Upgrade de tier y Private Endpoint quedan como decisión post-MVP, a tomar cuando exista producto/tráfico real, **sin gatillo numérico predefinido**.

## Alternativas consideradas

- **Tier pagado (M10+) desde el inicio**: descartado — costo innecesario antes de validar tráfico/ingresos reales.
- **MongoDB autoalojado sobre Container Apps**: descartado — carga operativa de administrar backups/parches/HA no se justifica para 1 desarrollador; Atlas gestiona eso incluso en el tier gratuito.

## Consecuencias

- Cluster compartido, sin Private Endpoint — riesgo aceptado explícitamente para el MVP, documentado en [`docs/security/threat-model.md`](../../security/threat-model.md).
- Los límites de conexión/almacenamiento de M0 deben monitorearse a medida que crezca el uso del piloto; no hay un umbral numérico predefinido que dispare el upgrade — es una decisión de producto/negocio post-MVP.

## Referencias

- [ADR 0018 — MongoDB Atlas como almacén de datos](0018-mongodb-atlas-datastore.md).
- [`docs/security/threat-model.md`](../../security/threat-model.md).
