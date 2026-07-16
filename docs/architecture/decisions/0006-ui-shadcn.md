# ADR 0006: UI con shadcn/ui + Tailwind

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica (recomendación de herramental adoptada como parte del plan aprobado)

## Contexto

Un solo desarrollador frontend necesita construir una UI consistente y accesible (WCAG 2.1 AA es criterio de aceptación de la Fase 26) en un plazo de 8-12 semanas, incluyendo componentes complejos como tablas comparativas (`TanStack Table`).

## Decisión

shadcn/ui + Tailwind CSS + TanStack Table como base de componentes.

## Alternativas consideradas

- **MUI (Material UI)**: descartado — mayor esfuerzo de override de theming para lograr una identidad visual propia distinta de Material Design.
- **Construir componentes desde cero**: descartado — demasiado lento para el plazo disponible con 1 desarrollador.

## Consecuencias

- Los componentes de shadcn/ui se copian al repositorio (no se instalan como dependencia versionada de npm), lo que significa actualizaciones manuales cuando shadcn publique cambios relevantes.
- Al estar construido sobre Radix UI, shadcn/ui da una base accesible por defecto, lo que facilita cumplir el criterio de WCAG 2.1 AA de la Fase 26.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 9.
