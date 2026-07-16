# ProcuraWise — Despliegue

Este documento describe el diseño de despliegue aprobado. **Ninguna infraestructura real existe todavía** — se aprovisiona a partir de la Fase 27 (ver [`docs/development/backlog.md`](../development/backlog.md)). Hasta entonces, todo el desarrollo corre 100% local vía Docker Compose.

## Ambientes

| Ambiente | Infraestructura | Cuándo existe | Propósito |
|---|---|---|---|
| Local | Docker Compose: Mongo, Azurite, Redis, Mailhog | Desde Fase 0 | Desarrollo con datos sintéticos, sin Azure real |
| Development | CI (GitHub Actions), recursos económicos | Desde que exista `.github/workflows/` (Fase 0 en adelante para lint/test; despliegue real Fase 27) | Validación automatizada en cada PR |
| Staging | Azure real, similar a producción | Desde Fase 27 | E2E, UAT antes del piloto |
| Production | Azure Container Apps, aprobaciones, backups, alertas, mínimo privilegio | Desde Fase 27-28 | Piloto (Fase 28) y operación real |

## Recursos Azure por ambiente (diseño aprobado, aún no aprovisionado)

- **Azure Container Apps**: hosting de API y worker (ver [ADR 0019](../architecture/decisions/0019-azure-container-apps-hosting.md)).
- **MongoDB Atlas**: tier M0 (free) con IP allowlist para todo el MVP (ver [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md)).
- **Azure Blob Storage**: almacenamiento de documentos (Azurite como equivalente local).
- **Azure Service Bus**: cola de jobs asíncronos en staging/producción (Redis como equivalente local, ver [ADR 0005](../architecture/decisions/0005-worker-asincrono-service-bus.md)).
- **Azure Key Vault**: gestión de secretos vía identidad administrada — sin secretos en código ni en GitHub.
- **Azure Container Registry**: imágenes firmadas/escaneadas.
- **Azure Communication Services**: notificaciones reales (desde Fase 24).
- **Azure OpenAI / Foundry**: `AIProvider` (desde Fase 13); Foundry Web Search desactivado por flag hasta aprobación legal (ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md)).

## Pipeline CI/CD (diseño aprobado)

- **IaC**: Bicep (ver [ADR 0004](../architecture/decisions/0004-bicep-vs-terraform.md)), carpetas `/infra/{bicep,params,scripts}`.
- **CI/CD**: GitHub Actions con OIDC federado a Azure — sin secretos de larga vida en el repositorio.
- **Pipelines objetivo**: `lint.yml`, `test.yml` (desde Fase 0, contra smoke test de `/health`), `deploy-staging.yml`, `deploy-prod.yml` (desde Fase 27).
- **Registro de imágenes**: Azure Container Registry, imágenes firmadas y escaneadas antes de desplegar.

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
