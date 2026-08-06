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

Subpaquetes autocontenidos bajo `service/procurawise/`, mapeados a las entidades y módulos de API de la especificación (§17): `identity`, `evaluations`, `vendors`, `proposals`, `qna`, `scoring`, `tco`, `decisions`, `reports`, `documents`, `notifications`, `ai`, `curated_sources`, `agreements`, `billing`, `admin`, `audit`, `shared`.

`curated_sources` (Fase 14) es una excepción deliberada a la tabla de forma interna de abajo: no tiene `router.py` propio — sus endpoints viven en `admin/router.py` (CLAUDE.md §4: rutas `platform_admin` en un router físicamente separado), y `curated_sources.service.CuratedSourceService` no usa `audit.service.AuditEventService` porque `AuditEvent` es intrínsecamente tenant-scoped (`AuditEventRepository` siempre escribe vía `TenantCollection`) y `CuratedSource` es contenido de plataforma sin `tenant_id`.

`agreements` (Fase 15) es otra excepción deliberada: no tiene `router.py` propio — sus dos endpoints (`GET/POST /vendor-portal/agreements/status|accept`) viven en `vendor_portal/agreements_router.py` (solo un proveedor autenticado los consume, mismo router físicamente separado que ya exige CLAUDE.md §4); tampoco tiene `exceptions.py` (no hay condición de error propia más allá de lo que Pydantic ya valida). El resto de la lógica de auth/invitación de proveedor (`VendorInvitation`, `VendorAuthService`) vive dentro de `identity/` en vez de un módulo `vendors/` separado — `VendorOrganization` ya vivía ahí desde antes de Fase 15 y no se extrajo (recomendación no bloqueante de la sesión de planeación de Fase 15, no comprometida para ninguna fase futura concreta).

`documents` (Fase 16) tiene un único `router.py`, pero con **dos** `APIRouter` distintos dentro (`vendor_documents_router`, bajo `/vendor-portal/proposals/{proposal_id}/documents`, gateado por `require_agreements_accepted`; `buyer_documents_router`, bajo `/evaluations/{evaluation_id}/proposals/{proposal_id}/documents`, `BUYER_READ_ROLES`, sin ninguna ruta de escritura registrada) — separación física de lectura/escritura por rol dentro del mismo módulo, no CLAUDE.md §4 (que aplica a proveedor vs. `platform_admin`, no aplicable aquí). Tampoco tiene `exceptions.py` propio (viven en `service.py`, mismo criterio que `agreements`) ni `events.py`. La única novedad de infraestructura: `AzureBlobStorage.generate_download_url()` (`shared/storage.py`) genera una Service SAS de solo lectura (permiso `read=True` únicamente) firmada con la account key del connection string — deliberadamente no una User Delegation SAS, que requiere Azure AD/managed identity y no funciona contra Azurite, rompiendo la paridad dev/prod que el resto del proyecto mantiene. El contenedor de Blob dedicado (`documents_container_name`, distinto del genérico que ya usa el health check) se autoprovisiona de forma perezosa y cacheada en el primer request que lo necesita (`documents/router.py::get_document_service`), no vía `shared/migrations.py::run_migrations()` — ese módulo es solo-índices-Mongo y nunca se invoca automáticamente por `make dev`/`make test-integration`/CI, así que atar ahí la provisión de Blob no habría resuelto el problema para ningún flujo real.

`qna` (Fase 17) tiene un único `router.py`, con **dos** `APIRouter` distintos dentro (`vendor_qna_router`, bajo `/vendor-portal/proposals/{proposal_id}/questions`, gateado por `require_agreements_accepted`; `buyer_qna_router`, bajo `/evaluations/{evaluation_id}/questions`, lectura `BUYER_READ_ROLES`/escritura `OWNER_ONLY`) — mismo patrón de separación física de lectura/escritura por rol que `documents`. Grano: **un documento Mongo por pregunta** (`Question`, colección `qna_questions`), con la respuesta actual y su historial embebidos (`current_answer: AnswerVersion | None`, `answer_history: list[AnswerVersion]`) — no una colección `qna_answers` separada, mismo patrón que `Proposal`/`ProposalAnswer` para relaciones 1-a-pocos que nunca se consultan independientemente de su padre. La anonimización de preguntas publicadas es una garantía de tipos, no un filtro en tiempo de ejecución: `PublicQuestionResponse` (lo que ve un proveedor distinto del autor) simplemente no declara ningún campo de identidad, a diferencia de `VendorQuestionResponse` (propia) y `BuyerQuestionResponse` (comprador, identidad real siempre visible). "Notificaciones" en esta fase no introduce ningún mecanismo nuevo — reutiliza el propio `AuditEvent` best-effort ya emitido en cada mutación más un segundo consumidor real de `PollingController`/[ADR 0012](decisions/0012-polling-adaptativo.md) en el frontend (`useQnaPolling.ts`), sin entidad `Notification`, sin canal de entrega real, sin bounded context `notifications/` (ese sigue siendo Fase 24).

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
- **`Document`** (`documents/`, Fase 16): metadata en Mongo (`tenant_id`, `evaluation_id`, `proposal_id`, `vendor_org_id`, `requirement_id` opcional — evidencia puntual y adjuntos generales de propuesta coexisten, decisión de planeación D1 —, `version`, `status: current|superseded`, `filename`, `content_type`, `size_bytes`, `sha256`, `blob_key`, `scan_status`), bytes en Azure Blob Storage/Azurite (spec §16.1). "Slot" reemplazable/versionado = `(proposal_id, requirement_id)`; un adjunto general (`requirement_id=null`) nunca reemplaza a otro. Nunca se sobrescribe un `blob_key` ya usado — cada versión tiene el suyo propio, la anterior queda `status="superseded"` sin borrarse. `ProposalSnapshot.document_ids` congela qué documentos `current` existían al momento de enviar la propuesta (los ids, no una copia de su metadata — el `Document` propio, ya inmutable tras envío, sigue siendo la fuente de verdad).
- **`Question`** (`qna/`, Fase 17): un documento por pregunta (`tenant_id`, `evaluation_id`, `proposal_id`, `vendor_org_id`, `requirement_id` opcional, `scope: requirement|general`, `body`, `status: open|answered|withdrawn`, `version` — concurrencia optimista del documento completo, mismo patrón que `Proposal`), con `current_answer`/`answer_history` embebidos como `AnswerVersion` (`version`, `body`, `visibility: private|published_anonymized`, `answered_by_membership_id`, `answered_at`) — cada versión anterior queda congelada e inspeccionable, nunca se sobrescribe. Escritura (crear/retirar/responder) solo mientras `Evaluation.status == "collecting_responses"`; sin campo de deadline dedicado, el gate real es el propio estado de la evaluación.
- **`Score.source_ai_execution_id`** (`scoring/`, Fase 18): campo opcional aditivo — `None` en todo score puramente manual (pasado y futuro); apunta al `AIExecution` cuya sugerencia originó el valor cuando el evaluador la usó como punto de partida (aceptada tal cual o editada). Nunca escrito por `ai/`, siempre por el propio `PUT` de score ya existente; `ScoringService` deriva "accepted"/"modified" comparando server-side, nunca confía en una declaración del cliente.
- **`FXRate`** (`tco/`, Fase 19): colección compartida, no tenant-scoped, gestionada solo por `platform_admin`, mismo patrón que `CuratedSource` (Fase 14) — sin `TenantCollection`, sin UI dedicada (`{from_currency, to_currency, rate, effective_date, source: "manual", created_by_admin_id}`). Create-only: sin endpoint de edición/borrado, para que una tasa ya congelada en algún `ProposalSnapshot.tco_result` nunca pueda alterarse retroactivamente. Ver [ADR 0008](decisions/0008-fuente-fx-tco.md).
- **`CostItem`** (`tco/`, Fase 19): partida de costo de libre autoría del proveedor (sin plantilla definida por el comprador), embebida en `Proposal.cost_items` — mismo patrón que `ProposalAnswer`, no una colección separada. `category` restringido a las 3 categorías fijas del spec §8.1 (`initial | recurring | variable_extraordinary`); todos los campos monetarios (`quantity`, `unit_price`, `tax_pct`, `discount_pct`, `annual_increment_pct`) son `Decimal`/`Decimal128` — primer módulo del proyecto en usar `Decimal` para dinero (el resto del sistema, p. ej. las respuestas tipo `currency` de `proposals`, usa `float`). `Evaluation` gana `base_currency`/`tco_horizon_years` (config de la evaluación, no de la propuesta).
- **`TcoResult`** (`tco/`, Fase 19): value object calculado por `TcoService.calculate()` (función pura, sin acceso a Mongo) y congelado dentro de `ProposalSnapshot.tco_result` en el mismo momento que `ProposalService.submit()` ya congela `requirements`/`answers`/`document_ids` — nunca se recalcula después. `TcoService` nunca consulta `FXRateRepository` por sí misma; quien llama resuelve y le pasa las tasas ya frozen (`FrozenFxRate`), garantizando estructuralmente que una actualización posterior de `FXRate` no pueda alcanzar un TCO ya congelado (criterio de aceptación de la fase).
- **Versionado de propuestas** (`proposals/`, Fase 21 — completo): `Proposal.snapshot: ProposalSnapshot | None` (slot único, Fase 9-20) reemplazado por `Proposal.snapshots: list[ProposalSnapshot]` (append-only, máximo 2 — Ronda 0 + una única Ronda 1 opcional de negociación) + `Proposal.round: int`, campo deliberadamente separado de `Proposal.version` (concurrencia optimista, se incrementa en cada edición individual, no solo en submit). `ProposalAnswer` gana `status: inherited | modified` + `source_proposal_version`; `CostItem` (`tco/`) gana el mismo par más `removed` (a diferencia de una respuesta, que siempre corresponde 1:1 a un Requirement nunca eliminable, un costo sí admite alta/baja libre — un `CostItem` `removed` que traza a una ronda anterior queda como tombstone en el arreglo en vez de borrarse físicamente, para no perder historial). Reabrir una propuesta enviada (`ProposalService.reopen()`, solo `evaluation_owner`, FR-047) **reutiliza** `Evaluation.status="collecting_responses"` + `Proposal.status="draft"` — ningún estado nuevo — porque `documents/`/`qna/`/la escritura de respuestas y costos en `proposals/` ya gatean exactamente sobre esos dos valores. Ver [ADR 0013](decisions/0013-versionado-propuestas-negociacion.md).
- **Decisión final** (`decisions/`, Fase 22 — completo): `Decision` (colección propia `decisions`, grain 1:1 con `Evaluation`, `_id` determinístico = `evaluation_id`, mismo truco de `EvaluationSnapshot`) — estado propio (`not_requested | pending | approved | rejected`, misma forma que `ApprovalStatus` de Fase 12, `rejected` no terminal), `outcome: selected | void`, selección de proveedor derivada server-side (`selected_proposal_id`/`selected_proposal_snapshot_id` desde `Proposal.current_snapshot`, nunca aceptados del cliente), `justification`. Solo puede crearse/editarse mientras `Evaluation.status == "completed"` — hereda gratis todas las precondiciones de completitud de scoring/económico ya validadas por `complete_evaluation()` (Fase 20), sin reabrir esa lógica. **`Decision.approver_membership_id` es un campo propio, nunca copiado de ni escrito hacia `Evaluation.approver_membership_id`** (founder, sesión de planeación de Fase 22): la aprobación de publicación (Fase 12) y la aprobación de decisión (Fase 22) son dos actos independientes con su propio actor/estado/timestamps, aunque reutilizan el mismo patrón de validación (`ApproverRoleMismatchError`/`SelfApprovalError`, bloqueo de autoaprobación por `user_id`). Al aprobar, se congela `DecisionSnapshot` ("memo de cierre" — colección propia `decision_snapshots`, mismo patrón insert-only/`snapshot_id` determinístico/"flip status luego snapshot" que `EvaluationSnapshot`), que copia (no referencia) `ScoringService.get_results()` en el instante de aprobar para que un `Score`/`FXRate` posterior nunca pueda alterar retroactivamente una decisión ya aprobada. Sin ranking calculado ni persistido — mismo principio ya aplicado en `get_results()` desde Fase 18.
- **Reportes/exports** (`reports/`, Fase 23 — completo): `Report` (colección propia `reports`, grain 1:N insert-only por evaluación — cada solicitud de generación es un documento nuevo, "regenerar" nunca sobrescribe), mismo contrato de job asíncrono `queued | running | succeeded | failed` que `AIExecution` (Fase 13, [ADR 0012](decisions/0012-polling-adaptativo.md)). 8 tipos de reporte (`rfp_document`, `requirements_matrix`, `vendor_comparison`, `scoring_detail`, `risk_analysis`, `tco_breakdown`, `decision_record`, `qna_summary`), ensamblados por funciones puras (`reports/assembly.py`) contra una representación intermedia genérica (`ReportDocument`/`ReportWorkbook`) que desacopla el dominio de los 4 renderers (`reportlab`/`python-docx`/`openpyxl`/`csv` stdlib — [ADR 0023](decisions/0023-generacion-reportes-pdf-xlsx-docx.md)), mismo principio de frontera que la de proveedores de IA (CLAUDE.md §5.1: solo `reports/renderers/` importa las librerías de generación). Persistencia en un container de Blob propio (`procurawise-reports`, separado de `documents/`), descarga vía SAS bajo demanda. Readiness gateada por tipo — `decision_record` es el único con precondición dura (`Decision.status=="approved"`), consumiendo `DecisionSnapshot` (Fase 22) ya persistido sin recalcular nada. Import de Requirements (Excel/CSV, preview+mapeo) vive en el mismo bounded context (`reports/import_*.py`) y reutiliza `EvaluationRepository.add_requirements_bulk` (Fase 11) como tercer productor de Requirements, sin un camino de escritura propio.
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
    /scoring /tco /decisions /reports /documents /notifications
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
- **`AIUseCase = "score_suggestion"`** (Fase 18): segundo caso de uso de `AIExecution`, ya anticipado por el comentario original del propio `Literal` en Fase 13. Ruta más simple que `requirement_generation` — no usa `ResearchProvider` (no hay discovery de fuentes externas, el input es la propia respuesta ya congelada del proveedor en `ProposalSnapshot`), y el punto de "aceptación humana" **no es un endpoint de `ai/`** sino el `PUT .../scores/{requirement_id}` ya existente de `scoring/` (`ScoreWriteRequest.source_ai_execution_id` opcional) — la IA nunca importa ni llama a `ScoreRepository`. El worker generaliza de un topic fijo (`ai-requirement-generation`) a un dispatch real por topic (`ai.worker.build_dispatch_table`), consumiendo también `ai-score-suggestion`. Política de datos (qué campos de `ProposalAnswer`/`Requirement` se envían y cuáles nunca) documentada en [ADR 0022](decisions/0022-politica-datos-evaluacion-asistida-ia.md).
- **`tco/`** (Fase 19 — TCO base, completo): bounded context nuevo, ya anticipado en la lista de subpaquetes desde el diseño original. `TcoService.calculate()` es una función pura (sin dependencias de infraestructura) que implementa la única fórmula de agregación confirmada por el founder para los 3 tipos de costo (`monto(Y) = cantidad × precio_unitario × frecuencia_anual × (1+incremento_anual)^(Y-año_inicio) × (1-descuento)`). Fase 20 consumió `TcoResult.grand_total` de cada proveedor para la normalización 70% (`menor TCO / TCO proveedor × 100`, spec §7.5) sin tocar este módulo, exactamente como se anticipaba aquí.
- **`EconomicAssessment`** (Fase 20 — scoring económico completo): vive en `scoring/` (no un bounded context nuevo — es scoring, junto a `Score`), no una extensión de `Score` (atado a `requirement_id`, sin análogo cuando no hay Requirements). `Dimension` gana el valor `"economic"`; `RequirementDimension` (`functional`/`technical`) se introduce como tipo más estrecho para que un `Requirement` económico sea estructuralmente irrepresentable (`DIMENSION_MAX_POINTS` deliberadamente no gana una entrada `"economic"` — ver threat-model.md). `scoring/economic_formulas.py` son funciones puras (TCO normalizado, rúbricas 0-5 ponderadas, agregado 0-40) sin dependencias de infraestructura, mismo principio que `TcoService.calculate()`. La autorización reutiliza `Assignment`/`enforce_section_assignment` (Fase 9/18) con un sentinel fijo `section="economic"`, sin un segundo mecanismo de permisos.
- **Ronda de negociación** (Fase 21 — completo, ADR 0013): `Score` no cambió de grano — ya vivía por `snapshot_id` en su clave natural desde Fase 9, pero ningún read path lo explotaba hasta ahora. La invalidación ("modificar una respuesta invalida su score") se resuelve enteramente en lectura: `ScoringService._scores_for_current_snapshot()` calcula, para cada propuesta, los scores del snapshot vigente más un *fallback* al snapshot anterior únicamente para respuestas `status=="inherited"` sin score propio todavía en la ronda actual — sin copiar ni reescribir ningún `Score` físicamente. `EconomicAssessment` (Fase 20) gana `snapshot_id` en su clave natural pero **sin** fallback equivalente — se recaptura por completo cada ronda, decisión deliberada porque es una rúbrica de 10 criterios fijos sobre la propuesta entera (no por-requirement) y su componente TCO (70% del score) cambia estructuralmente en cuanto hay `CostItem`s modificados. `SnapshotResponse` (`proposals/schemas.py`) expone `cost_items`/`tco_result` de cada ronda — necesario para que la vista de comparación del frontend (`ProposalVersionComparisonPage.tsx`) pueda diferenciar Ronda 0 vs. Ronda 1 sin un endpoint de diff dedicado.

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
- **Decisión final** (Fase 22 — completo): bounded context nuevo (`decisions/`), ya anticipado en la lista de subpaquetes desde el diseño original (§3/§9). Sin adjudicación automática por construcción — ninguna transición a `Decision.status="approved"` ocurre sin una llamada HTTP autenticada del `approver` propio de la decisión (nunca el de publicación). `reports/` (Fase 23) ya consume `DecisionSnapshot` para el tipo `decision_record`, sin recalcular nada retroactivamente; notificaciones reales (Fase 24) queda como el próximo consumidor.
- **Reportes/exports + import de requerimientos** (Fase 23 — completo): bounded context nuevo (`reports/`), ya anticipado en la lista de subpaquetes desde el diseño original (§3/§9). Generación siempre asíncrona vía el mismo worker/dispatch table genérico ya usado por `ai/` (`shared/worker_loop.py`, nuevo — loop genérico independiente de `ai/worker.py`, que queda intacto por restricciones de su propio test). Punto de extensión evidente para una fase futura: un noveno tipo de reporte (p. ej. exportar auditoría) solo requiere una función `assemble_*` nueva más su combinación de renderer, sin tocar el resto del pipeline.
- **MFA NO es un punto de extensión activo.** Fue removido del proyecto, no solo diferido — no hay ganchos ni flags preparados para él. Si se retoma, se evalúa desde cero en una versión futura independiente. Ver [ADR 0014](decisions/0014-mfa-excluido-conflicto-interes-eula.md).

## 11. Referencias

- Plan aprobado completo: [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md)
- Alcance del MVP: [`docs/product/mvp-scope.md`](../product/mvp-scope.md)
- Modelo de amenazas: [`docs/security/threat-model.md`](../security/threat-model.md)
- Despliegue: [`docs/operations/deployment.md`](../operations/deployment.md)
- ADRs: [`docs/architecture/decisions/`](decisions/)
