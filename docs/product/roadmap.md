# ProcuraWise — Roadmap

Ver desglose fase-por-fase con historias y criterios de aceptación en [`docs/development/backlog.md`](../development/backlog.md). Este documento muestra los bloques con objetivo blando de fecha y el criterio para pasar de fase.

## Objetivo de calendario

8-12 semanas, 1 desarrollador, sesiones separadas de Claude Code (~29 fases, cada una ≈ 1 sesión). Sin fecha dura por fase — el objetivo es la secuencia y las dependencias, no el calendario.

## Bloques del MVP

| Bloque | Fases | Objetivo |
|---|---|---|
| 0 — Fundación | 0, VS-2A, AUTH-PROD | Bootstrap, `identity`/multi-tenant con identidad de desarrollo (VS-2A), auth productiva (AUTH-PROD) |
| 1 — Vertical slice | VS-2A, VS-2B, VS-2C | Evaluación → requerimiento → invitación simulada → propuesta → scoring manual → **primer demo end-to-end**, usando identidad de desarrollo en vez de auth productiva |

> **Nota de secuencia (2026-07-27):** el vertical slice (antes numerado como Fases 1, 3-7) se construye con un `DevelopmentIdentityProvider` en vez de auth real, por lo que `AUTH-PROD` (antes "Fase 2 — Auth local") se pospone hasta después de cerrar VS-2C. Ver el detalle de IDs y trazabilidad en la tabla E1/E2 de [`backlog.md`](../development/backlog.md).
| 2 — Colaboración y auditoría | 8-12 | Audit trail, RBAC completo, wizard estático, biblioteca de requerimientos, publicación con snapshot |
| 3 — IA y proveedores reales | 13-16 | `AIProvider` real (biblioteca interna), `ResearchProvider` completo (Foundry tras flag), NDA/conflicto de interés reales, documentos |
| 4 — Q&A y validación | 17-18 | Q&A, evaluación asistida por IA |
| 5 — Decisión | 19-23 | TCO, scoring económico completo, ronda de negociación, decisión, reportes |
| 6 — Hardening y despliegue | 24-28 | Notificaciones reales, billing/admin P1, hardening, infra Azure real, piloto UAT |

## Criterio para pasar de fase

Una fase se considera cerrada cuando cumple la "definición de terminado" de [`CLAUDE.md`](../../CLAUDE.md): código + tests correspondientes + `docs/development/current-phase.md` y `docs/development/session-handoff.md` actualizados + lint/typecheck verde + demo manual verificada contra el criterio de aceptación de esa fase en `backlog.md`. No se avanza a la siguiente fase con criterios de aceptación pendientes salvo decisión explícita documentada como deuda técnica en `session-handoff.md`.

## Nota transversal: revisión legal de web-grounding

Corre en paralelo desde la Fase 1 como workstream del founder/abogado externo, sin bloquear ninguna fase de desarrollo. Su único gate real: `FoundryWebSearchProvider` no se activa (feature flag) en la Fase 14 sin aprobación documentada. Cronograma de referencia: conclusión preliminar antes de la Fase 7, aprobación final ≥2 semanas antes del piloto (Fase 28).

## Roadmap post-MVP (referencia direccional, no compromiso de fecha)

Las fases 2/3/4 de la especificación original (§25) permanecen como referencia direccional de hacia dónde crece el producto después del MVP. Los ítems etiquetados "fase posterior" en [`docs/product/mvp-scope.md`](mvp-scope.md) (CFDI, MFA, import Word/PDF, RFI/RFQ, firma legal, integraciones ERP, app móvil, subastas, WebSockets/tiempo real, rondas de negociación adicionales) son **candidatos a una versión futura independiente**, planeada y trabajada por separado — no ítems comprometidos dentro de los bloques 0-6 de este roadmap.

## Hitos de decisión pendientes fuera del roadmap técnico

- Aprobación legal de web-grounding (ver nota transversal arriba) — condiciona únicamente la activación de `FoundryWebSearchProvider`, no el desarrollo.
- Revisión post-MVP de tier de MongoDB Atlas (M0 → superior) y Private Endpoint, cuando exista producto/tráfico real (sin gatillo numérico predefinido, ver [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md)).
