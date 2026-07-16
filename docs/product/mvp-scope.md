# ProcuraWise — Alcance del MVP

Fuente: `docs/requirements/ProcuraWise_Especificacion_Producto_MVP.docx` (spec aprobada) + [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md) (plan aprobado 2026-07-16).

## Dentro de alcance del MVP

- Flujo RFP completo: entrevista guiada → requerimientos homologados → invitación hasta 6 proveedores → NDA → Q&A → propuestas con envío inmutable → evaluación 0-5 asistida por IA (score final humano) → TCO 1-5 años → ronda opcional de negociación (Ronda 0 + Ronda 1) → decisión aprobada por humano → cierre con reportes auditables.
- SaaS multi-tenant, idiomas ES/EN, máx. 6 proveedores por evaluación.
- Autenticación propia: email+password + OIDC Microsoft/Google (compradores), invitación por token (proveedores). Sin MFA.
- Import de requerimientos/catálogos: **solo Excel/CSV**, con preview y mapeo.
- IA: generación/descubrimiento de requerimientos usando `InternalKnowledgeProvider` (biblioteca interna, sin red externa) como P0; evaluación asistida (riesgos/score sugerido) con aceptar-o-modificar obligatorio.
- `ResearchProvider` con `CuratedSourceProvider` implementado; `FoundryWebSearchProvider` implementado pero **desactivado por defecto** (feature flag, requiere aprobación legal — P1 condicionado, ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md)).
- **Conflicto de interés dentro del alcance del MVP** (excepción explícita a §2.3 de la spec, decisión del founder): pantalla de aceptación tipo EULA al iniciar la respuesta del proveedor, vía el mismo mecanismo `Agreement` que la NDA.
- TCO con FX congelado por snapshot, actualización manual de tasas por `platform_admin`.
- Scoring económico completo: TCO normalizado 70%, condiciones comerciales 15%, riesgo/predictibilidad 15% (ver [ADR 0009](../architecture/decisions/0009-rubricas-economicas.md)); fórmula final Funcional 40%/Técnico 20%/Económico 40% + flags eliminatorios.
- Actualizaciones de estado vía polling adaptativo (no tiempo real vía WebSockets/SSE).
- Notificaciones reales (Azure Communication Services) en fase tardía del MVP (Fase 24); log/consola en fases tempranas.
- Billing/Admin básico P1: Stripe checkout, consola admin cross-tenant auditada (Fase 25 — tardía, no bloquea el vertical slice).
- Hardening de seguridad, accesibilidad WCAG 2.1 AA, infraestructura Azure real y piloto UAT (Fases 26-28).
- GDPR activado condicionalmente cuando el proveedor participante está basado en la UE.
- Retención de datos: default 1 año post-cierre de evaluación (no configurable por tenant en el MVP).
- NFR-003: 50 usuarios concurrentes, global de la plataforma (no por-tenant).

## Fuera de alcance del MVP (candidatos a versión futura independiente)

Estos ítems son "fase posterior" en el sentido definido por el plan aprobado: **una versión futura del producto, planeada y trabajada de forma independiente** — no un compromiso de fecha dentro de este roadmap.

- Import de Word/PDF (solo Excel/CSV en el MVP).
- MFA (eliminado del proyecto, no solo diferido — no hay puntos de extensión activos para él).
- CFDI.
- RFI/RFQ.
- Firma legal electrónica.
- Integraciones ERP.
- App móvil.
- Subastas.
- **Adjudicación automática — excluida permanentemente**, no es un ítem de fase posterior sino una regla de producto no negociable (human-in-the-loop).
- Búsqueda web en vivo como dependencia P0: reclasificada a P1 condicionado a aprobación legal (ver contradicción documentada en el plan aprobado, sección 5).
- WebSockets/SSE/Azure SignalR para tiempo real (arquitectura deja el punto de extensión abierto, no implementado en el MVP).
- Upgrade de tier MongoDB Atlas / Private Endpoint (decisión post-MVP sin gatillo numérico predefinido).
- Retención de datos configurable por tenant.
- Rondas de negociación adicionales más allá de Ronda 0 + Ronda 1.

## Gaps de la especificación original y su resolución

Todos los gaps identificados durante la revisión arquitectónica quedaron resueltos por decisiones explícitas del founder (sesiones 2026-07-15 y 2026-07-16), documentadas con dueño y fecha en [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md), sección 4, y formalizadas en los ADRs correspondientes (0003, 0008, 0009, 0010, 0011, 0012, 0013, 0014, 0015, 0016). No quedan preguntas bloqueantes para iniciar la Fase 0.

## Contradicción aceptada explícitamente

FR-022 (§6.3 de la spec, originalmente marcado P0) queda reclasificado a P1 condicionado a la aprobación legal de web-grounding. Detalle completo y justificación en `approved-mvp-plan.md`, sección 5. Ningún criterio de aceptación del MVP depende de búsqueda web en vivo.
