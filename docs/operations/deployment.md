# ProcuraWise — Despliegue

Este documento describe el diseño de despliegue aprobado. **Ninguna infraestructura real existe todavía** — se aprovisiona a partir de la Fase 27 (ver [`docs/development/backlog.md`](../development/backlog.md)). Hasta entonces, todo el desarrollo corre 100% local vía Docker Compose.

## Ambientes

| Ambiente | Infraestructura | Cuándo existe | Propósito |
|---|---|---|---|
| Local | Docker Compose: Mongo, Azurite por defecto; perfil opcional `servicebus` (emulador de Azure Service Bus + SQL Server, Fase 13) vía `make dev-up-servicebus`. Cola: `InMemoryMessageBus` en proceso por defecto, `ServiceBusMessageBus` contra el emulador si `queue_backend=service_bus` (ver [ADR 0020](../architecture/decisions/0020-composicion-servicios-desarrollo-local.md) y [ADR 0021](../architecture/decisions/0021-ai-provider-abstraction.md)) | Desde Fase 1B (perfil `servicebus` desde Fase 13) | Desarrollo con datos sintéticos, sin Azure real |
| Development | CI (GitHub Actions), recursos económicos | Desde Fase 1C (`.github/workflows/`; despliegue real Fase 27) | Validación automatizada en cada PR |
| Staging | Azure real, similar a producción | Desde Fase 27 | E2E, UAT antes del piloto |
| Production | Azure Container Apps, aprobaciones, backups, alertas, mínimo privilegio | Desde Fase 27-28 | Piloto (Fase 28) y operación real |

## Recursos Azure por ambiente (diseño aprobado, aún no aprovisionado)

- **Azure Container Apps**: hosting de API y worker (ver [ADR 0019](../architecture/decisions/0019-azure-container-apps-hosting.md)).
- **MongoDB Atlas**: tier M0 (free) con IP allowlist para todo el MVP (ver [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md)).
- **Azure Blob Storage**: almacenamiento de documentos (Azurite como equivalente local).
- **Azure Service Bus**: cola de jobs asíncronos en staging/producción, adaptador real (`ServiceBusMessageBus`) implementado desde Fase 13 (`shared/messaging.py`, `queue_backend=service_bus` — ver [ADR 0005](../architecture/decisions/0005-worker-asincrono-service-bus.md), [ADR 0020](../architecture/decisions/0020-composicion-servicios-desarrollo-local.md) y [ADR 0021](../architecture/decisions/0021-ai-provider-abstraction.md)). El emulador oficial (`mcr.microsoft.com/azure-messaging/servicebus-emulator:2.0.1` + `mcr.microsoft.com/mssql/server:2022-CU26-ubuntu-22.04`, pinned) vive en `docker-compose.yml` bajo el perfil opcional `servicebus` (`make dev-up-servicebus` / `make test-integration-ai`) — no es requisito de `make dev`/`make test`/`make dev-up`, siguiendo la disciplina de ADR 0020 de no levantar infraestructura sin consumidor concreto en el arranque por defecto.
- **Azure Key Vault**: gestión de secretos vía identidad administrada — sin secretos en código ni en GitHub. En producción, `azure_openai_api_key` y `service_bus_connection_string` se resuelven desde Key Vault, nunca desde `.env`.
- **Azure Container Registry**: imágenes firmadas/escaneadas.
- **Azure Communication Services**: notificaciones reales (desde Fase 24).
- **Azure OpenAI / Foundry**: `AIProvider` implementado desde Fase 13 (`AzureOpenAIProvider`, sobre el SDK oficial `openai`). Config requerida en producción (`Settings._require_real_ai_config_in_production`): `azure_openai_endpoint`, `azure_openai_api_key`, `azure_openai_deployment` — ninguno tiene default fuera de `production`, así que el despliegue falla explícitamente si falta alguno en vez de arrancar con IA silenciosamente deshabilitada. Foundry Web Search (`FoundryWebSearchProvider`, Fase 14) desactivado por flag hasta aprobación legal (ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md)) — distinto del `AIProvider`/Azure OpenAI de esta fase.

## Pipeline CI/CD

- **IaC**: Bicep (ver [ADR 0004](../architecture/decisions/0004-bicep-vs-terraform.md)), carpetas `/infra/{bicep,params,scripts}` — a partir de Fase 27.
- **CI/CD de despliegue** (diseño aprobado, no implementado todavía): GitHub Actions con OIDC federado a Azure — sin secretos de larga vida en el repositorio. `deploy-staging.yml`/`deploy-prod.yml` llegan en Fase 27.
- **CI/CD de calidad e integración** (implementado desde Fase 1C, 2026-07-18): `.github/workflows/ci.yml` (lint, typecheck, tests unitarios backend/frontend, build de producción del frontend, verificación de que el contrato OpenAPI/cliente TS generado no está desactualizado — ver [ADR 0007](../architecture/decisions/0007-contratos-openapi-orval.md)), `.github/workflows/integration.yml` (pruebas contra Mongo+Azurite reales), `.github/workflows/security.yml` (secret scanning con `gitleaks`, dependency scanning con `pip-audit`/`pnpm audit`). Reemplaza el boceto original `lint.yml`/`test.yml` — se consolidó en `ci.yml` con jobs separados por responsabilidad (`backend`/`frontend`/`contracts`) para no duplicar checkout/setup entre workflows disparados por el mismo evento, y se separó `integration.yml` para no acoplar la señal rápida de lint/typecheck al arranque de contenedores Docker. Ningún job usa secretos; todos corren con `permissions: contents: read`. Detalle completo del diseño y de las Actions pinneadas por SHA en `docs/development/session-handoff.md` (entrada de Fase 1C).
- **Registro de imágenes**: Azure Container Registry, imágenes firmadas y escaneadas antes de desplegar — a partir de Fase 27.

## Gestión de secretos

Azure Key Vault vía identidad administrada. Ningún secreto se comitea al repositorio ni se configura como GitHub Secret de larga vida — la autenticación de CI/CD a Azure usa OIDC federado.

## Migraciones de base de datos (diseño aprobado)

Carpeta `migrations/` numerada + colección de control `_migrations` + `indexes.py` por módulo como fuente de verdad, aplicado idempotentemente al arrancar el servicio.

## Rollback

A definir en detalle durante la Fase 27 (aprovisionamiento de infra real), como parte del mismo trabajo que define `deploy-staging.yml`/`deploy-prod.yml`. Principio general aprobado: todo despliegue a producción debe ser reversible sin pérdida de datos; Container Apps soporta revert a la revisión anterior.

## Backup / restore

Diseño aprobado, verificación programada antes del piloto (Fase 26, como parte de Hardening — ver [`docs/development/backlog.md`](../development/backlog.md)). No hay todavía una prueba de backup/restore ejecutada, porque no existe infraestructura real.

## Runbook

A construirse durante la Fase 27-28, una vez que exista infraestructura real que operar. Este documento se actualizará en esa fase con el runbook operativo real (no un runbook especulativo sobre infraestructura que aún no existe).

## Última prueba de backup/restore

Ninguna — no aplica todavía, no hay infraestructura real. Se actualizará este campo la primera vez que se ejecute, en la Fase 26.

## Referencias

- [`docs/architecture/architecture.md`](../architecture/architecture.md), sección 7.
- [ADR 0004](../architecture/decisions/0004-bicep-vs-terraform.md), [ADR 0019](../architecture/decisions/0019-azure-container-apps-hosting.md).
