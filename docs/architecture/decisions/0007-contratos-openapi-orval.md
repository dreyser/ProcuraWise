# ADR 0007: Estrategia de contratos frontend/backend — OpenAPI + orval

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

Hay un solo frontend (React+TS) y un solo backend (FastAPI) controlados por el mismo desarrollador/equipo. Se necesita un contrato tipado entre ambos que no se desactualice silenciosamente.

## Decisión

El contrato es el `openapi.json` que FastAPI genera automáticamente desde los `schemas.py` (Pydantic). `make contracts` corre `orval` para generar tipos TypeScript + hooks de React Query, comprometidos al repositorio. CI verifica que no estén desactualizados (`git diff --exit-code` tras regenerar). No se crea `packages/contracts` ni `packages/ui` como paquetes de monorepo compartido.

## Alternativas consideradas

- **Pact / contract-testing dedicado**: descartado — diseñado para múltiples equipos/servicios consumiendo un contrato de forma independiente; con un solo equipo controlando ambos lados, el costo de mantenimiento no se justifica.
- **`packages/contracts` compartido en un monorepo**: descartado — abstracción de monorepo JS innecesaria cuando solo hay un frontend y un backend; el `openapi.json` generado ya cumple ese rol.

## Consecuencias

- Todo cambio de API requiere correr `make contracts` antes de continuar el trabajo de frontend dependiente.
- CI bloquea merges si los tipos generados no coinciden con el `openapi.json` actual — evita que el contrato se desactualice silenciosamente.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 8.
