# ADR 0011: Abstracción `ResearchProvider` + gate legal para Foundry Web Search

**Estado:** Accepted (para la abstracción `ResearchProvider` e `InternalKnowledgeProvider`/`CuratedSourceProvider`) / Proposed-Condicional (para la activación de `FoundryWebSearchProvider`)
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

La especificación (§9) ya recomendaba un "adaptador intercambiable" para búsqueda web. La revisión legal de qué datos pueden enviarse a un proveedor de búsqueda web externo (Microsoft Foundry Web Search) no está completa al momento de este plan, y FR-022 (§6.3) estaba originalmente marcado P0 dentro de un rango "todos P0".

## Decisión

Interfaz única `ResearchProvider` con tres implementaciones:
- **`InternalKnowledgeProvider`** (default obligatorio, biblioteca + documentos autorizados, sin red externa) — **P0, Accepted**.
- **`CuratedSourceProvider`** (lista administrada de URLs/fuentes aprobadas, sin búsqueda abierta, requiere aprobación de términos) — **Accepted**.
- **`FoundryWebSearchProvider`** (Microsoft Foundry Web Search real) — implementado pero **desactivado por defecto** vía feature flag por ambiente y luego por tenant, solo activable tras aprobación legal explícita; nunca fallback automático si falla (degrada a `InternalKnowledgeProvider` e lo indica en la UI) — **Proposed/Conditional**.

Gobernanza: Accountable = founder/Product Owner; Responsible = abogado externo; Consulted = responsable técnico + seguridad. La revisión inicia en paralelo a la Fase 1, conclusión preliminar antes de la Fase 7, aprobación final ≥2 semanas antes del piloto (Fase 28); se repite si cambia proveedor/términos/región/datos/arquitectura. Política de datos: nunca se envían datos personales, nombre del cliente, proveedores participantes, respuestas/precios/propuestas, documentos cargados, información contractual/confidencial ni secretos — solo consultas abstractas y sanitizadas por categoría.

Como consecuencia directa, **FR-022 queda reclasificado de P0 a P1 condicionado**, con aprobación explícita del founder (ver contradicción documentada en `docs/planning/approved-mvp-plan.md`, sección 5).

## Alternativas consideradas

- **No incluir ninguna abstracción de búsqueda web, solo `InternalKnowledgeProvider` hardcodeado**: descartado — la spec explícitamente pide un camino adaptable hacia búsqueda web futura (§9).
- **Activar `FoundryWebSearchProvider` por defecto desde el inicio**: descartado — sin aprobación legal, riesgo crítico de exposición de datos según §24 de la spec.

## Consecuencias

- Ningún criterio de aceptación del MVP depende de búsqueda web en vivo funcionando.
- El caso de uso "Generación" de IA (§9) se angosta en el MVP a "contexto+biblioteca→candidatos" si la aprobación legal no llega a tiempo — aceptado explícitamente por el founder.
- Activar el flag de `FoundryWebSearchProvider` sin aprobación legal documentada está explícitamente prohibido (ver [`CLAUDE.md`](../../../CLAUDE.md)).

## Referencias

- Backlog, Fases 13-14.
- [`docs/product/mvp-scope.md`](../../product/mvp-scope.md).
