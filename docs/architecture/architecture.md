# ProcuraWise — Arquitectura

Este documento describe la arquitectura aprobada del MVP. Ninguna decisión aquí descrita se reabre sin un ADR nuevo en [`docs/architecture/decisions/`](decisions/) (ver regla en [`CLAUDE.md`](../../CLAUDE.md)).

## 1. Visión de componentes

```
┌─────────────────┐        ┌──────────────────────────────┐
│  apps/web         │ HTTP  │  service/procurawise/api        │ ← FastAPI, síncrono
│  React + TS (SPA)  │──────▶│  (routers → services → repos) │
└─────────────────┘        └───────────────┬──────────────┘
                                              │ misma base de código,
                                              │ llamada directa a service.py
                            ┌───────────────▼──────────────┐
                            │  service/procurawise/worker     │ ← jobs asíncronos
                            │  (dispatch table)              │
                            └───────────────┬──────────────┘
                                              │
                    ┌──────────────┬─────────┴────────┬──────────────┐
                    ▼              ▼                   ▼              ▼
              MongoDB Atlas   Azure Blob /       Redis (dev) /   Azure OpenAI /
              (M0 en MVP)     Azurite (dev)      Service Bus     Foundry
                                                  (prod)
```

API síncrona (FastAPI) y worker asíncrono comparten el mismo paquete de dominio `procurawise` — nunca hay lógica de negocio duplicada entre ambos. Ver [ADR 0001](decisions/0001-monolito-modular.md) y [ADR 0005](decisions/0005-worker-asincrono-service-bus.md).

## 2. Empaquetado

Un solo proyecto Python (`service/`), un solo `pyproject.toml`/entorno virtual (gestionado con `uv`). API y worker son entrypoints delgados sobre el mismo paquete `procurawise`. El frontend (`apps/web`) es una SPA React+TS independiente, servida por separado (Vite en desarrollo). Ver [ADR 0017](decisions/0017-frontend-react-typescript.md).

## 3. Bounded contexts ↔ entidades

Subpaquetes autocontenidos bajo `service/procurawise/`, mapeados a las entidades y módulos de API de la especificación (§17): `identity`, `evaluations`, `vendors`, `proposals`, `qna`, `scoring`, `tco`, `decisions`, `documents`, `notifications`, `ai`, `curated_sources`, `agreements`, `billing`, `admin`, `audit`, `shared`.

`curated_sources` (Fase 14) es una excepción deliberada a la tabla de forma interna de abajo: no tiene `router.py` propio — sus endpoints viven en `admin/router.py` (CLAUDE.md §4: rutas `platform_admin` en un router físicamente separado), y `curated_sources.service.CuratedSourceService` no usa `audit.service.AuditEventService` porque `AuditEvent` es intrínsecamente tenant-scoped (`AuditEventRepository` siempre escribe vía `TenantCollection`) y `CuratedSource` es contenido de plataforma sin `tenant_id`.

`agreements` (Fase 15) es otra excepción deliberada: no tiene `router.py` propio — sus dos endpoints (`GET/POST /vendor-portal/agreements/status|accept`) viven en `vendor_portal/agreements_router.py` (solo un proveedor autenticado los consume, mismo router físicamente separado que ya exige CLAUDE.md §4); tampoco tiene `exceptions.py` (no hay condición de error propia más allá de lo que Pydantic ya valida). El resto de la lógica de auth/invitación de proveedor (`VendorInvitation`, `VendorAuthService`) vive dentro de `identity/` en vez de un módulo `vendors/` separado — `VendorOrganization` ya vivía ahí desde antes de Fase 15 y no se extrajo (recomendación no bloqueante de la sesión de planeación de Fase 15, no comprometida para ninguna fase futura concreta).

Cada bounded context sigue la misma forma interna:

| Archivo | Responsabilidad |
|---|---|
| `models.py` | Entidades de dominio |
| `schemas.py` | Contratos Pydantic (fuente del `openapi.json`) |
| `repository.py` | Acceso a datos, siempre `tenant_id`-scoped vía `TenantCollection` |
| `service.py` | Lógica de negocio — lo que el worker importa directamente, sin HTTP interno |
| `router.py` | Endpoints FastAPI |
| `events.py` | Eventos de dominio emitidos por el context |
| `exceptions.py` | Errores tipados del context |

**Regla de dependencia:** `router.py` → `service.py` → `repository.py`, nunca al revés. El worker llama `service.py` por función directa — evita el anti-patrón de "microservicio disfrazado". No reabrir sin ADR (ver [ADR 0001](decisions/0001-monolito-modular.md)).

## 4. Flujo síncrono vs. jobs asíncronos

Operaciones interactivas (CRUD, login, scoring manual) van por la API síncrona y responden directamente. Operaciones largas o costosas (generación IA, reportes, imports) se despachan al worker: la API responde `202 Accepted` con `{job_id, status_url}` y el estado se consulta por **polling adaptativo** desde el cliente — no hay WebSockets/SSE/SignalR en el MVP. Contrato completo, incluyendo comportamiento de backoff, pausa en pestaña oculta y manejo de offline, en [ADR 0012](decisions/0012-polling-adaptativo.md).

Cola: `InMemoryMessageBus` (dentro del proceso) en desarrollo local, Azure Service Bus en staging/producción, mismo contrato `MessageBus`/dispatch table en el worker. Ver [ADR 0005](decisions/0005-worker-asincrono-service-bus.md) y [ADR 0020](decisions/0020-composicion-servicios-desarrollo-local.md) (cambio del default local, Fase 1B).

## 5. Multi-tenancy

Ver detalle de amenazas y controles en [`docs/security/threat-model.md`](../security/threat-model.md). Resumen estructural:

- **`tenant_id`** proviene exclusivamente de un claim del JWT — nunca de body/query/header del cliente. Si el cliente envía un `tenant_id` distinto al del claim, se rechaza con 400.
- Multi-organización usa `/api/v1/auth/switch-tenant`, que reemite un JWT nuevo para una sola organización activa: **un JWT = un tenant**.
- Dependencia FastAPI `get_current_context()` adjunta `tenant_id/user_id/roles` a `request.state`.
- Capa de repositorio reforzada estructuralmente vía `TenantCollection(db, "evaluations", tenant_id)`, que **inyecta automáticamente** `{"tenant_id": tenant_id}` en cada `find/find_one/update_one/delete_one` — estructuralmente imposible omitir el filtro.
- Todo índice compuesto de colección de negocio empieza con `tenant_id` (ej. `{tenant_id:1, evaluation_id:1}`).
- Usuarios proveedor (`vendor_contact`) se sirven desde router disjunto `/api/v1/vendor-portal/*` con su propia dependencia `get_current_vendor_context()` (`identity/jwt_provider.py`, `token_use="vendor_access"`, Fase 15). La garantía no es "chequear permisos" sino que **no existe código de ruta que enumere vendors ni evaluaciones ajenas**.
  > **Aclaración fechada (Fase 15, 2026-08-02, decisión de planeación D2):** el JWT de proveedor sí lleva `tenant_id` (`VendorOrganization` ya es tenant-owned — ver §6 abajo) pero **no** lleva una lista de `evaluation_id`s. La frase original de este párrafo ("reciben vendor_org_id + lista de evaluation_ids") se interpreta como descripción conceptual de alcance, no como mandato literal de claim: el alcance real (qué evaluaciones ve un proveedor) se resuelve en cada request vía `vendor_org_id`+`tenant_id` contra `TenantCollection`, por organización completa — no por evaluación individual. Un proveedor vinculado a una evaluación nueva después de emitido el JWT la ve de inmediato, sin necesitar un login nuevo. Esta aclaración no reabre la arquitectura (no cambia monolito/BD/hosting/patrón de comunicación, CLAUDE.md §3) — no ameritó ADR nuevo.
- Rol `platform_admin` sin `tenant_id` en el claim, rutas bajo `/api/v1/admin/*`, método explícito `find_across_tenants()` (no existe en el path normal), decorado con `@requires_audit_reason`.

Ver [ADR 0002](decisions/0002-multi-tenant-mongodb.md).

## 6. Modelo de datos (resumen)

MongoDB Atlas, tier M0 en el MVP (ver [ADR 0015](decisions/0015-tier-mongodb-atlas-m0.md) y [ADR 0018](decisions/0018-mongodb-atlas-datastore.md)). Entidades principales por bounded context según §17 de la especificación; mecanismos compartidos relevantes:

- **`Agreement`** (`agreements/`, Fase 15): registro append-only de aceptación (`type: nda | conflict_of_interest`, `user_id`, `ip`, `timestamp`, `version`), reutilizado para NDA y conflicto de interés — grano `user_id`, nunca `vendor_org_id` (cada colaborador acepta individualmente, ADR 0014). `VendorInvitation` (mismo módulo `identity/`) modela el token de invitación de un solo uso que crea la `Membership` `vendor_contact` antes de que exista ninguna aceptación. `VendorOrganization` **no** incluye todavía `country`/`region` para el flag de GDPR (pendiente, ver `docs/security/threat-model.md`, sección "Bandera GDPR" — corrección de una referencia previa incorrecta de este mismo documento).
- **`FXRate`**: colección compartida, no tenant-scoped, gestionada solo por `platform_admin` (`{from_currency, to_currency, rate, effective_date, updated_by, source: "manual"}`). Cada snapshot de TCO congela la tasa vigente al publicar/enviar. Ver [ADR 0008](decisions/0008-fuente-fx-tco.md).
- **Versionado de propuestas**: cada `ProposalAnswer` de una nueva versión registra `status: inherited | modified | removed` + `source_proposal_version`; un `Score` pertenece a una versión específica. Ver [ADR 0013](decisions/0013-versionado-propuestas-negociacion.md).
- **Migraciones**: carpeta `migrations/` numerada + colección `_migrations` de control + `indexes.py` por módulo como fuente de verdad, aplicado idempotentemente al arrancar.

## 7. Ambientes

| Ambiente | Infraestructura | Propósito |
|---|---|---|
| Local | Docker Compose (Mongo, Azurite) + `InMemoryMessageBus` en proceso | Desarrollo, datos sintéticos — Fases 0-26 |
| Development | CI, recursos económicos | Validación automatizada |
| Staging | Azure real, similar a producción | E2E, UAT — desde Fase 27 |
| Production | Azure Container Apps, aprobaciones, backups, alertas | Piloto y operación — Fase 28 |

Infra real solo se aprovisiona en la Fase 27; todo el desarrollo de los Bloques 0-5 corre 100% local. Ver [ADR 0019](decisions/0019-azure-container-apps-hosting.md) y [`docs/operations/deployment.md`](../operations/deployment.md).

## 8. Convenciones de API y contratos

El contrato entre frontend y backend es el `openapi.json` que FastAPI genera desde `schemas.py`. `make contracts` corre `orval` (`client: 'react-query'` desde VS-2C, sobre un mutator propio `apps/web/src/lib/http.ts`) para generar tipos TS + hooks de TanStack Query, comprometidos al repo; CI verifica que no estén desactualizados. No se crea `packages/contracts` ni `packages/ui` — abstracciones de monorepo innecesarias con un solo frontend y un solo backend. Ver [ADR 0007](decisions/0007-contratos-openapi-orval.md).

`GET /api/v1/vendor-organizations` (módulo `identity`, agregado en VS-2C) es el único endpoint de catálogo con paginación por cursor opaco (`(name, id)` estable) en el MVP — patrón de referencia si otro bounded context necesita paginar un catálogo tenant-scoped en el futuro.

## 9. Estructura de repositorio

UI construida con shadcn/ui + Tailwind + TanStack Table (ver [ADR 0006](decisions/0006-ui-shadcn.md)).

```
/apps/web                      # React + TS (Vite)
  /src/api                     # cliente generado (orval) — no editar a mano
  /src/features                 # por dominio: evaluations/, vendors/, proposals/, scoring/...
  /src/components                # shadcn/ui + compuestos propios
/service                       # monolito Python único (api + worker)
  /procurawise
    /identity /evaluations /vendors /proposals /qna
    /scoring /tco /decisions /documents /notifications
    /ai /curated_sources /agreements /billing /admin /audit /shared
    /api                       # FastAPI: main.py, router aggregation, middleware, deps.py
    /worker                    # main.py, dispatch table de jobs (real desde Fase 13 — ai-requirement-generation)
  /tests/{unit,integration,security,e2e_support}
  /migrations                   # migraciones numeradas, aplicadas idempotentemente vía `make migrate`
  pyproject.toml  uv.lock  Dockerfile.api  Dockerfile.worker
/infra
  /bicep  /params  /scripts
/docs
  /planning /product /development /architecture/decisions /security /operations
  /requirements (ya existe)
/.github/workflows
docker-compose.yml             # mongo, azurite (cola local en proceso: InMemoryMessageBus — ver ADR 0020);
                                # perfil opcional `servicebus` (Fase 13, ADR 0021): emulador de Azure Service Bus
Makefile                        # make dev/test/lint/contracts/migrate/dev-up-servicebus/test-integration-ai
CLAUDE.md  README.md
```

## 10. Puntos de extensión conocidos

- **`AIProvider`** (Fase 13): interfaz `typing.Protocol` para llamadas a un modelo de lenguaje, con `AzureOpenAIProvider` como única implementación del MVP. Un segundo proveedor (OpenAI directo, Anthropic, un modelo local) se agrega escribiendo una clase nueva contra el Protocol, sin tocar `ai.service` ni ningún módulo de dominio. Ver [ADR 0021](decisions/0021-ai-provider-abstraction.md).
- **`ResearchProvider`** (Fase 14 — completo): interfaz intercambiable, composición vía `ai.composite_research_provider.build_research_provider()`. `InternalKnowledgeProvider` es el default obligatorio (su fallo es un fallo duro del job); `CuratedSourceProvider` (biblioteca curada por `platform_admin`, plataforma no tenant-scoped) es siempre aditivo; `FoundryWebSearchProvider` (REST directo sobre `httpx`/`azure-identity`, sin SDK de agentes) se compone solo si `Settings.foundry_web_search_enabled` pasa el validador fail-closed (`foundry_legal_approval_reference` + endpoint + agent name, exigidos en **todo** ambiente) — **no activado en ningún ambiente del MVP**. Cualquier fuente secundaria que falle degrada a un `ResearchWarning` estructurado sin fallar el job (nunca texto crudo de excepción). Cada `discover()` produce `ResearchSnippet`s que se persisten, sin modificar, como el `source_catalog` inmutable de ese job (`AIExecution.source_catalog`) — la única fuente de verdad para las citaciones que ve un usuario; `AIRequirementCandidate.sources` solo referencia `source_id`s de ese catálogo, nunca una URL directamente del modelo. Ver [ADR 0011](decisions/0011-research-provider-gate-legal-foundry.md).

```text
Flujo de negocio (AIService.request_generation)
    ↓
AIService (ai/service.py) — orquesta discover → render → generate → validate → persist
    ↓
ResearchProvider (Protocol)         AIProvider (Protocol)
    ↓                                    ↓
CompositeResearchProvider          AzureOpenAIProvider
  ├─ InternalKnowledgeProvider     (SDK oficial `openai`, único adaptador
  ├─ CuratedSourceProvider          fuera de este diagrama que ve texto/JSON
  └─ FoundryWebSearchProvider       crudo del proveedor)
     (nunca activo en el MVP)
    ↓
ResearchSnippet[] + ResearchWarning[]  →  AIRequest (prompt versionado)
    ↓                                       ↓
source_catalog (persistido, inmutable)   AIResponse (raw_output + parsed_output)
    ↓                                       ↓
                              Validación de schema (Pydantic) + de negocio
                                            ↓
                        AIRequirementCandidate[] (sources ⊆ source_catalog ids)
                                            ↓
                         AIExecution.candidates (efímero, no es Requirement)
                                            ↓
                    Revisión y aceptación humana explícita (POST .../accept)
                                            ↓
                              Requirement real (Evaluation.requirements)
```

Ningún módulo fuera de `ai/` ve el texto/JSON crudo del proveedor, una excepción de su SDK, o una URL sin pasar por el `source_catalog` persistido — ver CLAUDE.md §5.1.
- **Polling → eventos futuros**: el contrato de job asíncrono deja el punto de extensión abierto para SSE/WebSockets/Azure SignalR en una versión futura, sin comprometerlo en el MVP. Ver [ADR 0012](decisions/0012-polling-adaptativo.md).
- **Más de 6 proveedores**: el límite de 6 es una regla de producto de la spec, no una limitación estructural de datos; ampliar el límite no requiere cambio de modelo, solo de validación.
- **MFA NO es un punto de extensión activo.** Fue removido del proyecto, no solo diferido — no hay ganchos ni flags preparados para él. Si se retoma, se evalúa desde cero en una versión futura independiente. Ver [ADR 0014](decisions/0014-mfa-excluido-conflicto-interes-eula.md).

## 11. Referencias

- Plan aprobado completo: [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md)
- Alcance del MVP: [`docs/product/mvp-scope.md`](../product/mvp-scope.md)
- Modelo de amenazas: [`docs/security/threat-model.md`](../security/threat-model.md)
- Despliegue: [`docs/operations/deployment.md`](../operations/deployment.md)
- ADRs: [`docs/architecture/decisions/`](decisions/)
