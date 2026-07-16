# ProcuraWise — Plan Aprobado del MVP

**Estado:** Aprobado por el founder el 2026-07-16.
**Origen:** Sesión de planeación arquitectónica de Claude Code (rol "arquitecto"), sobre la especificación `docs/requirements/ProcuraWise_Especificacion_Producto_MVP.docx`.
**Propósito de este documento:** ser la fuente de verdad persistente del plan aprobado. Los demás documentos en `docs/` (scope, roadmap, backlog, arquitectura, ADRs, threat-model, deployment) son la forma "viva" y desglosada de este plan; si hay una discrepancia entre ellos y este documento, gana el ADR correspondiente si existe, y si no, este documento.

---

## 1. Resumen del producto

ProcuraWise es un SaaS B2B multi-tenant que convierte una necesidad de compra de software/tecnología en un proceso RFP riguroso: entrevista guiada → requerimientos homologados (con ayuda de IA + investigación interna/curada) → invitación de hasta 6 proveedores → NDA + conflicto de interés → Q&A → propuestas con envío inmutable → evaluación 0-5 asistida por IA (score final siempre humano) → comparación TCO 1-5 años → ronda opcional de negociación → decisión aprobada por un humano (nunca adjudicación automática) → cierre con reportes auditables.

Principios que gobiernan todo el diseño técnico:
- **Human-in-the-loop no negociable**: la IA sugiere, el humano decide, en cada punto de contacto (requerimientos, scoring, descalificación, adjudicación).
- **Aislamiento estricto** proveedor↔proveedor↔comprador↔plataforma (riesgo crítico marcado en la spec, §24).
- **Inmutabilidad por versión**: snapshot al publicar RFP, snapshot al enviar propuesta, auditoría append-only.

## 2. Estado del repositorio al momento de este plan

Greenfield total: sin `.git`, sin código, sin infraestructura, sin CI. Único contenido: `docs/requirements/ProcuraWise_Especificacion_Producto_MVP.docx` (spec aprobada, 28 secciones).

## 3. Decisiones bloqueadas desde la especificación (§27, no se reabren)

Nombre=ProcuraWise; mercado México/LatAm; proceso RFP primero, categoría software/tecnología; SaaS multi-tenant; idiomas ES/EN; máx. 6 proveedores; pesos Funcional 40%/Técnico 20%/Económico 40%; TCO 1-5 años en MXN/USD; frontend React+TS; backend Python+FastAPI; datos MongoDB Atlas; hosting Azure Container Apps; IA Azure OpenAI/Foundry + búsqueda web con control humano; archivos Azure Blob; CI/CD GitHub Actions→Azure vía OIDC; comercial por-evaluación o suscripción; plazo 8-12 semanas.

## 4. Decisiones tomadas en sesiones de planeación (2026-07-15 y 2026-07-16)

1. **Autenticación propia** (authlib + OIDC directo a Microsoft/Google para compradores, JWT propio, invitación por token para proveedores). Ver [ADR 0003](../architecture/decisions/0003-autenticacion-propia.md).
2. **Alcance de importación: solo Excel/CSV en el MVP.** Word/PDF quedan para una versión futura independiente. Ver [ADR 0010](../architecture/decisions/0010-alcance-import-excel-csv.md).
3. **MongoDB Atlas tier M0 (free)** para todo el MVP, con IP allowlist; upgrade y Private Endpoint son decisión post-MVP sin gatillo numérico predefinido. Ver [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md).
4. **MFA eliminado del proyecto**, no solo diferido. Ver [ADR 0014](../architecture/decisions/0014-mfa-excluido-conflicto-interes-eula.md).
5. **Conflicto de interés entra al alcance del MVP** (contradice la exclusión original §2.3, decisión explícita del founder), como pantalla de aceptación tipo EULA al iniciar la respuesta del proveedor, reutilizando el mecanismo `Agreement` de la NDA. Ver ADR 0014.
6. **Actualizaciones en tiempo real: polling adaptativo**, no WebSockets/SSE/SignalR en el MVP. Ver [ADR 0012](../architecture/decisions/0012-polling-adaptativo.md).
7. **GDPR se activa cuando el proveedor participante está basado en la UE** (`VendorOrganization.country`/`region`).
8. **Revisión legal de web-grounding: gate de release, no gate de desarrollo.** Reclasifica FR-022 de P0 a P1 condicionado. Ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md).
9. **Rúbricas económicas definidas** (comercial 15%, riesgo/predictibilidad 15%, con sub-criterios y pesos). Ver [ADR 0009](../architecture/decisions/0009-rubricas-economicas.md).
10. **Ronda final de negociación**: Ronda 0 inicial (inmutable) + Ronda 1 opcional (negociación/BAFO), con versionado de respuestas. Ver [ADR 0013](../architecture/decisions/0013-versionado-propuestas-negociacion.md).
11. **Fuente de FX: actualización manual por `platform_admin`** sobre tabla compartida `FXRate`. Ver [ADR 0008](../architecture/decisions/0008-fuente-fx-tco.md).
12. **Retención de datos: default 1 año** post-cierre de evaluación, configurable por tenant a futuro (no en el MVP). Ver [ADR 0016](../architecture/decisions/0016-retencion-datos-1-anio.md).
13. **NFR-003 (50 usuarios concurrentes) confirmado global de la plataforma**, no por-tenant.
14. **Definición de "fase posterior"**: versión futura del producto, planeada y trabajada de forma independiente a esta entrega — no un ítem comprometido dentro de las fases 2/3/4 del roadmap original (§25). Aplica a CFDI, Word/PDF import, RFI/RFQ, MFA, y cualquier otro ítem etiquetado así.

**Herramental recomendado** (adoptado como parte de este plan): Bicep, pnpm, uv, Vitest+Testing Library, pytest, Playwright, OpenAPI+orval, shadcn/ui+Tailwind. Ver ADRs 0004, 0006, 0007.

No quedan preguntas bloqueantes: los ocho gaps identificados en la revisión previa fueron resueltos por las decisiones anteriores.

## 5. Contradicciones aceptadas explícitamente por el founder

Al reclasificar la búsqueda web en vivo de P0 a P1 condicionado:

1. **FR-022** (§6.3, dentro del rango marcado "todos P0") queda reclasificado a P1 condicionado, con aprobación del founder.
2. El caso de uso "Generación" de IA (§9) se angosta en el MVP a "contexto+biblioteca→candidatos" si la aprobación legal no llega a tiempo, vía `InternalKnowledgeProvider` como fallback obligatorio.
3. No hay contradicción arquitectónica: la spec (§9) ya recomendaba un adaptador intercambiable para búsqueda web; `ResearchProvider` formaliza esa recomendación.
4. El "hecho" del Bloque 3 del roadmap se redefine como: generación asistida por IA con biblioteca interna (P0) es suficiente; búsqueda web en vivo es un plus condicionado que no bloquea el resto del plan.
5. Sin contradicción de calendario: la revisión legal corre en paralelo desde la Fase 1 sin bloquear desarrollo; su único gate real es que `FoundryWebSearchProvider` no se active sin aprobación documentada (Fase 14).

## 6. Arquitectura aprobada (resumen)

Ver detalle completo en [`docs/architecture/architecture.md`](../architecture/architecture.md). Resumen: monolito modular (un solo paquete Python `procurawise`, entrypoints delgados para API síncrona FastAPI y worker asíncrono), frontend React+TS como SPA independiente, MongoDB Atlas con aislamiento multi-tenant estructural (`TenantCollection`), Azure Container Apps como hosting, cola local (Redis) en desarrollo / Azure Service Bus en producción para trabajos asíncronos con contrato de polling adaptativo en el cliente.

Bounded contexts (subpaquetes autocontenidos): `identity`, `evaluations`, `vendors`, `proposals`, `qna`, `scoring`, `tco`, `decisions`, `documents`, `notifications`, `ai`, `billing`, `admin`, `audit`, `shared`.

## 7. Estructura de repositorio objetivo

```
/apps/web                      # React + TS (Vite) — cliente generado, features por dominio
/service                       # monolito Python único (api + worker)
  /procurawise/{identity,evaluations,vendors,proposals,qna,
                scoring,tco,decisions,documents,notifications,
                ai,billing,admin,audit,shared}
  /procurawise/api              # FastAPI: main.py, router aggregation, middleware, deps.py
  /procurawise/worker           # main.py, dispatch table de jobs
  /tests/{unit,integration,security,e2e_support}
  pyproject.toml  uv.lock  Dockerfile.api  Dockerfile.worker
/infra/{bicep,params,scripts}
/docs                          # esta jerarquía (planning/, product/, development/,
                                # architecture/, security/, operations/)
/.github/workflows
docker-compose.yml             # mongo, azurite, redis, mailhog
Makefile                       # make dev/test/lint/contracts/migrate
CLAUDE.md  README.md
```

No se crea `packages/contracts` ni `packages/ui`: el contrato es el `openapi.json` que FastAPI genera desde `schemas.py`; `make contracts` corre `orval` para generar tipos TS + hooks, comprometidos al repo. Ver [ADR 0007](../architecture/decisions/0007-contratos-openapi-orval.md).

> **Nota:** esta ruta de documentación difiere de la propuesta original del plan (`docs/architecture.md` plano) porque la sesión de materialización documental (2026-07-16) usó la jerarquía `docs/{planning,product,development,architecture,security,operations}/` como alcance autorizado. El contenido es equivalente; solo cambió la ubicación de los archivos.

## 8. Fases del MVP

Ver desglose completo, fase por fase, en [`docs/development/backlog.md`](../development/backlog.md) y el objetivo de secuencia en [`docs/product/roadmap.md`](../product/roadmap.md). Resumen de bloques (~29 fases, cada una ≈ 1 sesión de Claude Code):

- **Bloque 0 — Fundación** (Fases 0-2): bootstrap, identity/multi-tenant, auth.
- **Bloque 1 — Vertical slice** (Fases 3-7): evaluación → requerimiento → invitación simulada → propuesta → scoring manual. Cierra en la Fase 7 con el primer demo end-to-end.
- **Bloque 2 — Colaboración y auditoría** (Fases 8-12): audit trail, RBAC, wizard estático, biblioteca de requerimientos, publicación con snapshot.
- **Bloque 3 — IA y proveedores reales** (Fases 13-16): `AIProvider` real con `InternalKnowledgeProvider`, `ResearchProvider` completo (Foundry desactivado por flag), NDA/conflicto de interés reales, documentos.
- **Bloque 4 — Q&A y validación** (Fases 17-18): Q&A, evaluación asistida por IA.
- **Bloque 5 — Decisión** (Fases 19-23): TCO, scoring económico completo, ronda de negociación, decisión, reportes.
- **Bloque 6 — Hardening y despliegue** (Fases 24-28): notificaciones reales, billing/admin, hardening, infra Azure real, piloto UAT.

## 9. Vertical slice recomendado

Fases 0-7: crear organización → crear evaluación básica → requerimiento manual → invitación simulada de proveedor (email = log a consola) → respuesta del proveedor vía portal con token → calificación manual 0-5 → resultado visible en tabla comparativa. Usa exclusivamente adaptadores locales (Mongo en Docker, sin Azure real, sin IA real, sin pagos). Primera demo end-to-end tangible, alcanzable en ~8 sesiones cortas.

## 10. Estrategia de pruebas (resumen)

Unit (scoring, TCO, permisos, máquina de estados, conversión de moneda) · Integration (Atlas/Mongo local, Azurite, cola, email, Stripe/IA vía mocks) · E2E Playwright (flujo completo) · Security (`test_tenant_isolation.py`, `test_vendor_isolation.py` en cada PR desde la Fase 1) · IA (datasets dorados, validación de schema, alucinación/inyección, costo) · Performance · Accesibilidad WCAG 2.1 AA (Fase 26) · Recuperación (backups/restore, Fase 26) · Negociación (Fase 21) · Polling/jobs asíncronos (Fase 13+).

Gate de calidad por fase: historias P0 requieren unit+integration; código no se considera "hecho" sin lint+typecheck verde.

## 11. Seguridad y multi-tenancy (resumen)

Ver detalle completo en [`docs/security/threat-model.md`](../security/threat-model.md). `tenant_id` exclusivamente del claim JWT, nunca de body/query/header del cliente. Wrapper `TenantCollection` inyecta automáticamente el filtro de tenant en cada operación Mongo. Proveedores servidos desde router disjunto `/api/v1/vendor-portal/*` sin `tenant_id` de comprador en su JWT. `platform_admin` sin `tenant_id`, rutas bajo `/api/v1/admin/*`, `find_across_tenants()` auditado con motivo obligatorio.

## 12. Riesgos y mitigaciones (resumen)

Fuga multi-tenant (crítico, mitigado desde Fase 1) · alucinaciones de IA (mitigado por regla "aceptar o modificar, score siempre humano") · exposición vía web-grounding (mitigado por `ResearchProvider` con fallback obligatorio y feature flag) · reclasificación de FR-022 (documentada, sin dependencia de MVP) · scope creep (mitigado por exclusiones explícitas en `mvp-scope.md`) · costo impredecible de IA (presupuestos y alertas) · uploads maliciosos (escaneo AV stub desde Fase 16) · tier gratuito de Mongo (riesgo aceptado, documentado) · dependencia del fundador como único desarrollador (mitigado por `session-handoff.md`/`current-phase.md`) · baja adopción de proveedores (riesgo de producto, a validar en el piloto).

## 13. Criterios para autorizar el inicio de implementación

1. Auth propia, alcance de import (Excel/CSV only), y las decisiones de la sección 4 de este documento — confirmadas, sin gaps bloqueantes.
2. Este plan, aprobado en su totalidad por el founder el 2026-07-16.
3. `git init` + primer commit ocurrirán como parte de la Fase 0 (acción no destructiva, primera acción real sobre el repo) — se confirmará explícitamente al inicio de esa sesión, no antes.
4. Antes de iniciar la Fase 1, el founder debe arrancar el engagement con el abogado externo para la revisión de web-grounding (workstream paralelo, no bloquea desarrollo).

Con estos puntos confirmados, la Fase 0 puede ejecutarse en una sesión nueva de Claude Code siguiendo el alcance exacto documentado en [`docs/development/current-phase.md`](../development/current-phase.md).
