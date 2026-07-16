# ADR 0010: Alcance de importación — solo Excel/CSV en el MVP

**Estado:** Accepted
**Fecha:** 2026-07-15 (reafirmado 2026-07-16)
**Origen:** Sesión de planeación arquitectónica

## Contexto

La especificación original no acotaba explícitamente los formatos de importación soportados. Soportar Word/PDF implica parsing/OCR de complejidad y riesgo considerables para un MVP de 8-12 semanas con 1 desarrollador.

## Decisión

Solo Excel/CSV son formatos de importación soportados en el MVP (con preview y mapeo de columnas, Fase 23). Word/PDF quedan pospuestos a una versión futura independiente, planeada y trabajada por separado.

## Alternativas consideradas

- **Soporte completo Word/PDF/Excel/CSV desde el MVP**: descartado — la complejidad de parsing/OCR confiable no se justifica dentro del plazo de 8-12 semanas.
- **Solo Excel, sin CSV**: descartado — CSV es más simple de parsear y ampliamente usado; el costo adicional de incluirlo es bajo frente al beneficio.

## Consecuencias

- Cualquier catálogo/requerimiento en Word o PDF debe convertirse manualmente a Excel/CSV por el usuario hasta que exista la versión futura que soporte esos formatos.
- Esto no es deuda técnica del MVP — es una exclusión de alcance documentada, ver [`docs/product/mvp-scope.md`](../../product/mvp-scope.md).

## Referencias

- Backlog, Fase 23.
