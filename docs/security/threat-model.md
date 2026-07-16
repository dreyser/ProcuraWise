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
- `tests/security/test_tenant_isolation.py` y `test_vendor_isolation.py` corren en **cada PR desde la Fase 1**, no solo antes del piloto: token de tenant A contra IDs de tenant B → 404 (no 403, para no confirmar existencia).

Detalle arquitectónico completo en [ADR 0002](../architecture/decisions/0002-multi-tenant-mongodb.md).

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
- **Pendientes (Fase 26 — Hardening):** rate limiting, CSRF, headers de seguridad, escaneo de secretos/dependencias en CI, WCAG 2.1 AA, pruebas de performance, backup/restore verificado.
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
