# ADR 0019: Hosting — Azure Container Apps

**Estado:** Accepted
**Fecha:** Bloqueado en la especificación aprobada (§27); documentado individualmente el 2026-07-16
**Origen:** Especificación de Producto MVP, §27 (decisión bloqueada, no reabierta en sesiones de planeación)

## Contexto

Esta decisión viene bloqueada desde la especificación de producto aprobada y no fue reabierta durante las sesiones de planeación arquitectónica. Se documenta aquí como ADR individual — distinto de [ADR 0004](0004-bicep-vs-terraform.md) (Bicep como IaC) — para dejar trazabilidad de la elección de la plataforma de cómputo/hosting en sí.

## Decisión

Azure Container Apps aloja los contenedores de API y worker en staging y producción.

**Nota de alcance (Fase 28, 2026-08-16):** el frontend (SPA React+TS, `apps/web/`) nunca tuvo una decisión de hosting propia — quedó fuera del alcance original de esta ADR (§27 solo mencionaba "API y worker") y `FRONTEND_BASE_URL`/`CORS_ALLOWED_ORIGINS` quedaron deliberadamente sin resolver en Fase 27 por esa razón. El founder resolvió esta pregunta bloqueante en la sesión de planeación de Fase 28: el frontend se sirve como un **tercer Container App**, dentro del mismo entorno ya provisionado (`modules/container-apps-env.bicep`), reutilizando el módulo Bicep genérico `modules/container-app.bicep` sin introducir un tipo de recurso Azure nuevo (se descartaron Azure Static Web Apps y hosting externo — Vercel/Netlify — por requerir cada uno un ADR propio). El contenedor sirve únicamente el build estático de Vite vía un servidor HTTP mínimo (nginx, sin proxy ni lógica de backend) — ver `apps/web/Dockerfile.web`/`apps/web/nginx.conf`. Esto no reabre la decisión de plataforma de esta ADR, solo extiende su alcance textual para cubrir el tercer workload. Diseñado para poder migrar después a Static Web Apps/CDN sin tocar contratos de API (`apiFetch` ya resuelve un origen de API configurable en build-time — `apps/web/src/lib/http.ts`).

## Alternativas consideradas

Ninguna evaluada en las sesiones de planeación original — la decisión se hereda tal cual de la especificación aprobada §27. Reabrirla (a nivel de plataforma api/worker) requiere un ADR nuevo que la sustituya explícitamente, con aprobación del founder.

Para el hosting del frontend (Fase 28) sí se evaluaron 3 opciones — ver nota de alcance arriba: (A) tercer Container App (elegida), (B) Azure Static Web Apps, (C) host externo (Vercel/Netlify).

## Consecuencias

- Se requiere despliegue containerizado (`Dockerfile.api`, `Dockerfile.worker`) a partir de la Fase 27, y (`Dockerfile.web`) a partir de la Fase 28.
- La infraestructura real solo se aprovisiona en esa fase; todo el desarrollo anterior (Bloques 0-5) corre 100% local vía Docker Compose.
- El frontend real (Fase 28) vive en el mismo Container Apps Environment que api/worker — mismo dominio por defecto (`*.<env>.<region>.azurecontainerapps.io`), distinto subdominio de app (`procurawise-web-{env}` vs. `procurawise-api-{env}`).

## Referencias

- [ADR 0004 — Bicep sobre Terraform](0004-bicep-vs-terraform.md).
- [`docs/operations/deployment.md`](../../operations/deployment.md).
