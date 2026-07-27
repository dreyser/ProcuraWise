# ProcuraWise — Modelo de amenazas

Este documento se actualiza a medida que avanzan las fases (se cierra formalmente en la Fase 26 — Hardening, según [`docs/development/backlog.md`](../development/backlog.md)). Hasta entonces refleja el diseño aprobado, no controles ya implementados (el repositorio es greenfield al momento de escribir este documento).

## Activos

- Datos de tenants compradores: evaluaciones, requerimientos, propuestas, scores, decisiones, documentos.
- Datos de proveedores: respuestas, precios, documentos, aceptaciones de NDA/conflicto de interés.
- Credenciales y JWT (compradores, proveedores, `platform_admin`).
- Tasas FX (`FXRate`), configuración de rúbricas económicas.
- Prompts, resultados y trazabilidad de ejecuciones de IA (`AIExecution`).
- Secretos de infraestructura (Azure Key Vault, credenciales de servicios externos).

## Actores y superficie de confianza por rol

| Rol | Alcance de confianza |
|---|---|
| Usuario comprador (tenant) | Solo datos de su propio tenant, vía `tenant_id` del JWT |
| Usuario proveedor | Solo `vendor_org_id` + evaluaciones a las que fue invitado, vía router disjunto `/vendor-portal` |
| `platform_admin` | Cross-tenant, solo vía `find_across_tenants()` auditado con motivo obligatorio |
| Sistema de IA (`AIProvider`/`ResearchProvider`) | Solo datos sanitizados/abstractos permitidos por política (ver [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md)) |

## Superficies de ataque

1. **API pública** (`/api/v1/*`) — autenticación, autorización, IDOR.
2. **Portal de proveedores** (`/api/v1/vendor-portal/*`) — acceso vía token de invitación, aislamiento de otras evaluaciones/proveedores.
3. **Uploads de documentos** — malware, tipo de archivo, tamaño, URLs temporales.
4. **IA / web-grounding** — exposición de datos confidenciales a un proveedor externo (ver riesgo crítico §24 de la spec).
5. **Webhooks** (Stripe, notificaciones) — validación de firma, replay.
6. **Panel `platform_admin`** — abuso de `find_across_tenants()`.

## Riesgo crítico #1: fuga multi-tenant

Marcado como riesgo crítico en la especificación (§24). Mitigación estructural, no solo por convención:

- `tenant_id` exclusivamente del claim JWT (nunca body/query/header del cliente).
- Wrapper `TenantCollection` inyecta automáticamente el filtro de tenant en cada operación Mongo.
- Router disjunto `/vendor-portal/*` sin `tenant_id` de comprador en el JWT de proveedor.
- `tests/security/test_tenant_isolation.py` y `test_vendor_isolation.py` corren en **cada PR desde VS-2A**, no solo antes del piloto: recurso de tenant A consultado desde tenant B → 404 (no 403, para no confirmar existencia).

Detalle arquitectónico completo en [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md).

**Estado de implementación (VS-2A, 2026-07-27):** `TenantCollection` (`service/procurawise/shared/tenant_collection.py`) implementado con las reglas descritas arriba más un control adicional: rechaza explícitamente cualquier intento de alterar `tenant_id` vía `$set`/`$setOnInsert`/`$unset` o reemplazo de documento, no solo vía filtro de lectura. El mecanismo de identidad (`DevelopmentIdentityProvider`, ver riesgo "Dev identity fuera de development" abajo) resuelve `tenant_id` desde una `Membership` persistida seleccionada por su propio `_id` (`X-Dev-Membership-Id`), nunca desde un valor de tenant enviado por el cliente. Pendiente de verificación contra Mongo real (sin Docker en la sesión de implementación) — ver `docs/development/current-phase.md`.

## Riesgos específicos del vertical slice (VS-2A/VS-2B)

| Riesgo | Mitigación | Estado |
|---|---|---|
| IDOR (acceso a un recurso de otro tenant por ID) | `TenantCollection` inyecta/valida `tenant_id` en cada operación; 404 uniforme | VS-2A implementado |
| Tenant escape vía colección compartida | `TenantCollection` rechaza colisión de filtro y mutación de `tenant_id` (`$set`/`$unset`/reemplazo) | VS-2A implementado |
| Enumeración de proveedores | `VendorOrganization` tenant-scoped (no hay directorio cross-tenant que enumerar) | VS-2A implementado |
| Escalación de rol | Rol resuelto server-side desde `Membership` por `membership_id`; el cliente nunca envía `tenant_id` ni `role` | VS-2A implementado |
| `DevelopmentIdentityProvider` habilitado fuera de development/test | Gate por `environment in (local, test)` → 404 en cualquier otro valor; test de integración explícito con `environment=production` | VS-2A implementado |
| Mass assignment (campos gestionados por el servidor enviados por el cliente) | Todo schema de escritura hereda `APIModel` (`extra="forbid"`) → 422 | VS-2A (`APIModel` base); pruebas por endpoint de escritura llegan con VS-2B (primeros endpoints de escritura de negocio) |
| NoSQL injection | Validación Pydantic de toda entrada antes de construir filtros Mongo | VS-2A (schemas de identity); se extiende en VS-2B |
| Manipulación de estado (saltar transiciones de `Evaluation`/`Proposal`) | Transiciones solo vía endpoints dedicados que validan el estado origen server-side (las 8 reglas explícitas del diseño) | Diseñado, implementación en VS-2B |
| Manipulación de score fuera de rango o por actor no autorizado | Solo `evaluator`/`owner`, solo durante `Evaluation.evaluating`, rango 0-5 validado, `requirement_id` debe existir en el `snapshot` de la propuesta | Diseñado, implementación en VS-2B |
| Fuga de información hacia el proveedor (scores, comentarios, otros proveedores) | Router de proveedor (`/vendor-portal/*`) físicamente separado, con schemas de respuesta propios que nunca incluyen `Score`/comentarios/otros proveedores | Diseñado, implementación en VS-2B |
| Logging de respuestas de propuesta | Disciplina de no pasar `answer.value`/`comment` como campo `extra` de logging estructurado | Diseñado, implementación en VS-2B |

## STRIDE por módulo crítico (resumen, se detalla en Fase 26)

| Módulo | Amenaza principal | Control previsto |
|---|---|---|
| `identity`/auth | Spoofing, elevación de privilegios | JWT propio + `tenant_id` como claim, sin confiar en input del cliente |
| `vendors`/vendor-portal | Repudiation, tampering de aceptación NDA/COI | `Agreement` con `user_id`/`ip`/`timestamp`/`version`, append-only |
| `proposals` | Tampering post-envío | Snapshot inmutable al enviar propuesta |
| `ai`/`ResearchProvider` | Information disclosure a terceros | Política de datos sanitizados, `FoundryWebSearchProvider` tras flag + aprobación legal (ADR 0011) |
| `admin` | Elevación de privilegios cross-tenant | `find_across_tenants()` explícito, auditado, con motivo obligatorio |
| `documents` | Malware, denial of service por tamaño | Escaneo AV stub (Fase 16), hardening real (Fase 26) |

## Controles existentes vs. pendientes

- **Existentes (diseñados, a implementar desde Fase 1):** aislamiento estructural de tenant, router disjunto de proveedores, snapshot inmutable, `Agreement` tipado.
- **Baseline de seguridad de pipeline (implementado desde Fase 1C, 2026-07-18):** secret scanning en cada PR/push a `main` vía `gitleaks` (`.github/workflows/security.yml`, job `secret-scan`, **bloqueante**), dependency vulnerability scanning vía `pip-audit` (Python) y `pnpm audit` (JS/pnpm) (jobs `python-deps`/`frontend-deps`, **informativo por ahora** — el repo es privado sin GitHub Advanced Security, y un árbol de dependencias recién creado tiene CVEs transitivos sin fix disponible que bloquearían PRs sin motivo real; política de bloqueo se revisita cuando haya bandwidth para triage regular), `Dependabot` para `pip`/`npm`/`github-actions`. **CodeQL no implementado** — no disponible gratis en un repo privado sin GHAS (requeriría hacer público el repo o adquirir GitHub Advanced Security); queda documentado aquí como mejora disponible, no como pendiente de una fase futura concreta.
- **Pendientes (Fase 26 — Hardening):** rate limiting, CSRF, headers de seguridad, promover dependency scanning de informativo a bloqueante (una vez exista bandwidth de triage regular), CodeQL si cambia la visibilidad del repo o se adquiere GHAS, SBOM, WCAG 2.1 AA, pruebas de performance, backup/restore verificado.
- **Pendientes de gate externo:** aprobación legal de web-grounding antes de activar `FoundryWebSearchProvider` (ver ADR 0011).

## Riesgos aceptados temporalmente

| Riesgo | Dueño | Fecha de revisión | Referencia |
|---|---|---|---|
| MongoDB Atlas tier M0 (cluster compartido, sin Private Endpoint) en producción | Founder | Post-MVP, sin gatillo numérico predefinido | [ADR 0015](../architecture/decisions/0015-tier-mongodb-atlas-m0.md) |
| Búsqueda web en vivo (`FoundryWebSearchProvider`) desactivada hasta aprobación legal | Founder / abogado externo | ≥2 semanas antes del piloto (Fase 28) | [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md) |
| Retención de datos fija a 1 año, no configurable por tenant | Founder | Post-MVP | [ADR 0016](../architecture/decisions/0016-retencion-datos-1-anio.md) |

## Bandera GDPR

`VendorOrganization.country`/`region` (capturado en la Fase 5) marca proveedores basados en la UE; solo esos activan el flujo de cumplimiento GDPR (residencia de datos, derecho al olvido). El resto de tenants no lo activa por default.

## Referencias

- [`docs/planning/approved-mvp-plan.md`](../planning/approved-mvp-plan.md), sección 11.
- [`docs/architecture/architecture.md`](../architecture/architecture.md), sección 5.
- [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md), [ADR 0011](../architecture/decisions/0011-research-provider-gate-legal-foundry.md).
