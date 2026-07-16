# ADR 0014: MFA excluido del proyecto + conflicto de interés como aceptación tipo EULA

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

La especificación original (§2.3, §27) difería tanto MFA como conflicto de interés a una fase posterior. El founder tomó, en esta sesión, dos decisiones explícitas que sustituyen esa posición: eliminar MFA por completo, y adelantar conflicto de interés al alcance del MVP.

## Decisión

- **MFA se elimina del proyecto**, no solo se difiere. No se diseñan puntos de extensión activos para MFA; si se retoma, será evaluado desde cero en una versión futura independiente.
- **Conflicto de interés entra al alcance del MVP** (excepción explícita a la exclusión original de §2.3) como una pantalla de aceptación independiente, estilo EULA/license agreement, presentada cuando un proveedor inicia su proceso de respuesta al RFP. Reutiliza el mismo mecanismo de registro de aceptación (`Agreement`) que la NDA: `type: nda | conflict_of_interest`, `user_id`, `ip`, `timestamp`, `version`.

## Alternativas consideradas

- **Mantener MFA como punto de extensión diferido pero diseñado**: descartado — agrega overhead de diseño ahora para una funcionalidad explícitamente despriorizada por el founder, que prefiere una remoción limpia a una deuda de diseño a medias.
- **Mantener conflicto de interés fuera del MVP según la spec original**: descartado — decisión explícita del founder de incluirlo, por consideraciones de riesgo legal/producto.

## Consecuencias

- No debe existir ningún campo, flag o gancho relacionado con MFA en el módulo `identity` — no es deuda técnica, es una exclusión de producto.
- El mecanismo `Agreement` se generaliza desde la Fase 15 para soportar ambos tipos desde el inicio, evitando un refactor posterior.

## Referencias

- [`docs/product/mvp-scope.md`](../../product/mvp-scope.md).
- Backlog, Fase 15.
