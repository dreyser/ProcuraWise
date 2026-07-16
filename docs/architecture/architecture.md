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

Subpaquetes autocontenidos bajo `service/procurawise/`, mapeados a las entidades y módulos de API de la especificación (§17): `identity`, `evaluations`, `vendors`, `proposals`, `qna`, `scoring`, `tco`, `decisions`, `documents`, `notifications`, `ai`, `billing`, `admin`, `audit`, `shared`.

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

Cola: Redis local en desarrollo, Azure Service Bus en staging/producción, mismo contrato de dispatch table en el worker. Ver [ADR 0005](decisions/0005-worker-asincrono-service-bus.md).

## 5. Multi-tenancy

Ver detalle de amenazas y controles en [`docs/security/threat-model.md`](../security/threat-model.md). Resumen estructural:

- **`tenant_id`** proviene exclusivamente de un claim del JWT — nunca de body/query/header del cliente. Si el cliente envía un `tenant_id` distinto al del claim, se rechaza con 400.
- Multi-organización usa `/api/v1/auth/switch-tenant`, que reemite un JWT nuevo para una sola organización activa: **un JWT = un tenant**.
- Dependencia FastAPI `get_current_context()` adjunta `tenant_id/user_id/roles` a `request.state`.
- Capa de repositorio reforzada estructuralmente vía `TenantCollection(db, "evaluations", tenant_id)`, que **inyecta automáticamente** `{"tenant_id": tenant_id}` en cada `find/find_one/update_one/delete_one` — estructuralmente imposible omitir el filtro.
- Todo índice compuesto de colección de negocio empieza con `tenant_id` (ej. `{tenant_id:1, evaluation_id:1}`).
- Usuarios proveedor no reciben `tenant_id` de comprador en su JWT — reciben `vendor_org_id` + lista de `evaluation_id`s a los que fueron invitados. Se sirven desde router disjunto `/api/v1/vendor-portal/*` con su propia dependencia `get_vendor_context()`. La garantía no es "chequear permisos" sino que **no existe código de ruta que enumere vendors ni evaluaciones ajenas**.
- Rol `platform_admin` sin `tenant_id` en el claim, rutas bajo `/api/v1/admin/*`, método explícito `find_across_tenants()` (no existe en el path normal), decorado con `@requires_audit_reason`.

Ver [ADR 0002](decisions/0002-multi-tenant-mongodb.md).

## 6. Modelo de datos (resumen)

MongoDB Atlas, tier M0 en el MVP (ver [ADR 0015](decisions/0015-tier-mongodb-atlas-m0.md) y [ADR 0018](decisions/0018-mongodb-atlas-datastore.md)). Entidades principales por bounded context según §17 de la especificación; mecanismos compartidos relevantes:

- **`Agreement`**: registro tipado de aceptación (`type: nda | conflict_of_interest`, `user_id`, `ip`, `timestamp`, `version`), reutilizado para NDA y conflicto de interés. `VendorOrganization` incluye `country`/`region` para el flag de GDPR.
- **`FXRate`**: colección compartida, no tenant-scoped, gestionada solo por `platform_admin` (`{from_currency, to_currency, rate, effective_date, updated_by, source: "manual"}`). Cada snapshot de TCO congela la tasa vigente al publicar/enviar. Ver [ADR 0008](decisions/0008-fuente-fx-tco.md).
- **Versionado de propuestas**: cada `ProposalAnswer` de una nueva versión registra `status: inherited | modified | removed` + `source_proposal_version`; un `Score` pertenece a una versión específica. Ver [ADR 0013](decisions/0013-versionado-propuestas-negociacion.md).
- **Migraciones**: carpeta `migrations/` numerada + colección `_migrations` de control + `indexes.py` por módulo como fuente de verdad, aplicado idempotentemente al arrancar.

## 7. Ambientes

| Ambiente | Infraestructura | Propósito |
|---|---|---|
| Local | Docker Compose (Mongo, Azurite, Redis, Mailhog) | Desarrollo, datos sintéticos — Fases 0-26 |
| Development | CI, recursos económicos | Validación automatizada |
| Staging | Azure real, similar a producción | E2E, UAT — desde Fase 27 |
| Production | Azure Container Apps, aprobaciones, backups, alertas | Piloto y operación — Fase 28 |

Infra real solo se aprovisiona en la Fase 27; todo el desarrollo de los Bloques 0-5 corre 100% local. Ver [ADR 0019](decisions/0019-azure-container-apps-hosting.md) y [`docs/operations/deployment.md`](../operations/deployment.md).

## 8. Convenciones de API y contratos

El contrato entre frontend y backend es el `openapi.json` que FastAPI genera desde `schemas.py`. `make contracts` corre `orval` para generar tipos TS + hooks React Query, comprometidos al repo; CI verifica que no estén desactualizados. No se crea `packages/contracts` ni `packages/ui` — abstracciones de monorepo innecesarias con un solo frontend y un solo backend. Ver [ADR 0007](decisions/0007-contratos-openapi-orval.md).

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
    /ai /billing /admin /audit /shared
    /api                       # FastAPI: main.py, router aggregation, middleware, deps.py
    /worker                    # main.py, dispatch table de jobs
  /tests/{unit,integration,security,e2e_support}
  pyproject.toml  uv.lock  Dockerfile.api  Dockerfile.worker
/infra
  /bicep  /params  /scripts
/docs
  /planning /product /development /architecture/decisions /security /operations
  /requirements (ya existe)
/.github/workflows
docker-compose.yml             # mongo, azurite, redis (cola local), mailhog
Makefile                        # make dev/test/lint/contracts/migrate
CLAUDE.md  README.md
```

## 10. Puntos de extensión conocidos

- **`ResearchProvider`**: interfaz intercambiable con tres implementaciones (`InternalKnowledgeProvider` default, `CuratedSourceProvider`, `FoundryWebSearchProvider` tras flag + aprobación legal). Ver [ADR 0011](decisions/0011-research-provider-gate-legal-foundry.md).
- **Polling → eventos futuros**: el contrato de job asíncrono deja el punto de extensión abierto para SSE/WebSockets/Azure SignalR en una versión futura, sin comprometerlo en el MVP. Ver [ADR 0012](decisions/0012-polling-adaptativo.md).
- **Más de 6 proveedores**: el límite de 6 es una regla de producto de la spec, no una limitación estructural de datos; ampliar el límite no requiere cambio de modelo, solo de validación.
- **MFA NO es un punto de extensión activo.** Fue removido del proyecto, no solo diferido — no hay ganchos ni flags preparados para él. Si se retoma, se evalúa desde cero en una versión futura independiente. Ver [ADR 0014](decisions/0014-mfa-excluido-conflicto-interes-eula.md).

## 11. Referencias

- Plan aprobado completo: [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md)
- Alcance del MVP: [`docs/product/mvp-scope.md`](../product/mvp-scope.md)
- Modelo de amenazas: [`docs/security/threat-model.md`](../security/threat-model.md)
- Despliegue: [`docs/operations/deployment.md`](../operations/deployment.md)
- ADRs: [`docs/architecture/decisions/`](decisions/)
