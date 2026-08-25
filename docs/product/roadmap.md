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

## Remediación UAT piloto (post-Fase 28, bloqueante para el piloto externo)

El primer UAT real end-to-end (Fase 28, 2026-08-24) expuso 20 hallazgos reales de producto/workflow/UX contra una evaluación completa de punta a punta. No estaba contemplado en este roadmap ni en `mvp-scope.md` — es trabajo concreto y secuenciado descubierto por el piloto real, no una reinterpretación del alcance ya cerrado del MVP ni parte del "roadmap post-MVP direccional" de abajo (que es sobre crecimiento futuro sin compromiso de fecha). Detalle completo (hallazgos, decisiones de producto A-I, bloques de implementación) en [`backlog.md`](../development/backlog.md#e12--remediación-uat-piloto-post-fase-28-no-numerado-en-el-planroadmap-original).

Secuencia aprobada, con dependencias reales entre bloques:

| Bloque | Hallazgos | Depende de |
|---|---|---|
| R1 (R1A/R1B/R1C) | UAT-01, 11, 16, 14, 10 | Fase 28 |
| R2 | UAT-06, 07, 08 (Reviewer + aprobación en dos pasos) | R1; **ADR 0026 obligatorio antes de implementar** |
| R3 | UAT-04, 09, 15 | R2 |
| R4 | UAT-02, 03, 05, 13, 17, 18, 19, 20 | Fase 28 (sin dependencia fuerte con R1/R2/R3) |

**Gate del piloto externo:** no se considera listo hasta que R1 y R2 estén completos, verificados con la suite completa, desplegados a staging, y validados manualmente con actores distintos (Owner → Reviewer → Approver → Owner publica/invita). R3/R4 quedan como mejoras deseables de MVP, no bloqueantes de este gate.

UAT-12 (descubribilidad de login comprador/proveedor) ya está cerrado (PR #62) — no forma parte de este remediation.

## Criterio para pasar de fase

Una fase se considera cerrada cuando cumple la "definición de terminado" de [`CLAUDE.md`](../../CLAUDE.md): código + tests correspondientes + `docs/development/current-phase.md` y `docs/development/session-handoff.md` actualizados + lint/typecheck verde + demo manual verificada contra el criterio de aceptación de esa fase en `backlog.md`. No se avanza a la siguiente fase con criterios de aceptación pendientes salvo decisión explícita documentada como deuda técnica en `session-handoff.md`.

## Nota transversal: revisión legal de web-grounding

Corre en paralelo desde la Fase 1 como workstream del founder/abogado externo, sin bloquear ninguna fase de desarrollo. Su único gate real: `FoundryWebSearchProvider` no se activa (feature flag) en la Fase 14 sin aprobación documentada. Cronograma de referencia: conclusión preliminar antes de la Fase 7, aprobación final ≥2 semanas antes del piloto (Fase 28).

**UAT-03 (R4, backlog.md):** Company Profile agregó el campo `website_url` con la intención explícita, ya aprobada por el founder, de que una fase posterior use ese sitio para investigar la empresa (ubicaciones, número de empleados, productos/servicios) y sugerir requerimientos relevantes. Esa investigación queda deliberadamente sin implementar en R4 — solo se guarda el dato. Cuando se construya, debe pasar por `ai.research_provider`'s `ResearchProvider` Protocol (nunca un fetch directo del campo desde un módulo de negocio, CLAUDE.md §5.1) y, si usa un proveedor con capacidad de búsqueda web, respeta el mismo gate legal de `FoundryWebSearchProvider` de este apartado.

## Roadmap post-MVP (referencia direccional, no compromiso de fecha)

Las fases 2/3/4 de la especificación original (§25) permanecen como referencia direccional de hacia dónde crece el producto después del MVP. Los ítems etiquetados "fase posterior" en [`docs/product/mvp-scope.md`](mvp-scope.md) (CFDI, MFA, import Word/PDF, RFI/RFQ, firma legal, integraciones ERP, app móvil, subastas, WebSockets/tiempo real, rondas de negociación adicionales) son **candidatos a una versión futura independiente**, planeada y trabajada por separado — no ítems comprometidos dentro de los bloques 0-6 de este roadmap.

También candidata a esta lista: investigación automática del sitio web de la empresa (campo `website_url` de Company Profile, UAT-03/R4) para sugerir ubicaciones/tamaño/productos relevantes al definir requerimientos — ver la nota legal de web-grounding arriba para el gate que aplica cuando se construya.

## Hitos de decisión pendientes fuera del roadmap técnico

- Aprobación legal de web-grounding (ver nota transversal arriba) — condiciona únicamente la activación de `FoundryWebSearchProvider`, no el desarrollo.
- Revisión post-MVP de tier de MongoDB Atlas (M0 → superior) y Private Endpoint, cuando exista producto/tráfico real (sin gatillo numérico predefinido, ver [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md)).
