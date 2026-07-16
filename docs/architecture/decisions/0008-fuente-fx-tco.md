# ADR 0008: Fuente de tasas de cambio (FX) para TCO

**Estado:** Accepted (actualizado 2026-07-16)
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

El cálculo de TCO 1-5 años en MXN/USD requiere una fuente consistente de tasas de cambio. La propuesta provisional original consideraba captura ad-hoc por el dueño de cada evaluación, lo que generaría tasas inconsistentes entre evaluaciones concurrentes.

## Decisión

Colección compartida `FXRate` (no tenant-scoped), gestionada exclusivamente por `platform_admin`, actualización manual: `{from_currency, to_currency, rate, effective_date, updated_by, source: "manual"}`. Cada `CostItem`/snapshot de TCO congela la tasa vigente al momento de publicación/envío — nunca recalcula con una tasa posterior.

## Alternativas consideradas

- **Integración con API de FX en vivo**: descartada para el MVP — costo/complejidad adicional no justificada; el control manual favorece la auditabilidad, un requisito explícito del producto.
- **Captura ad-hoc por el dueño de la evaluación (propuesta provisional original)**: descartada — genera tasas inconsistentes entre evaluaciones concurrentes y no hay una única fuente de verdad.

## Consecuencias

- `platform_admin` se convierte en un cuello de botella manual para mantener las tasas actualizadas — aceptable a la escala del MVP.
- Ninguna evaluación cambia su TCO retroactivamente cuando `FXRate` se actualiza después de que su snapshot fue tomado.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 6.
- Backlog, Fase 19.
