# ADR 0002: Estrategia multi-tenant en MongoDB

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

La fuga de datos entre tenants (comprador↔comprador, proveedor↔proveedor, comprador↔proveedor↔plataforma) está marcada como riesgo crítico en la especificación (§24). La mitigación no puede depender únicamente de disciplina de código — necesita ser estructural.

## Decisión

- `tenant_id` proviene exclusivamente de un claim del JWT, nunca de body/query/header del cliente; un valor distinto enviado por el cliente se rechaza (400).
- Multi-organización se resuelve vía `/api/v1/auth/switch-tenant`, que reemite un JWT nuevo para una sola organización activa — un JWT = un tenant.
- Wrapper `TenantCollection(db, "evaluations", tenant_id)` inyecta automáticamente `{"tenant_id": tenant_id}` en cada `find/find_one/update_one/delete_one` — estructuralmente imposible omitir el filtro.
- Todo índice compuesto de colección de negocio empieza con `tenant_id`.
- Proveedores se sirven desde router disjunto `/api/v1/vendor-portal/*` con `get_vendor_context()`, recibiendo `vendor_org_id` + `evaluation_id`s invitados, nunca `tenant_id` de comprador.
- `platform_admin` sin `tenant_id` en el claim, rutas bajo `/api/v1/admin/*`, `find_across_tenants()` explícito y auditado (`@requires_audit_reason`).
- `test_tenant_isolation.py` y `test_vendor_isolation.py` corren en cada PR desde la Fase 1, no solo antes del piloto.

## Alternativas consideradas

- **Base de datos separada por tenant**: descartada — incompatible con el tier gratuito M0 (ver [ADR 0015](0015-tier-mongodb-atlas-m0.md)) y con el costo operativo de administrar N bases para 1 desarrollador.
- **Filtrado manual a nivel de aplicación sin wrapper**: descartada — dado que la fuga multi-tenant es el riesgo crítico #1 de la spec, depender de que cada desarrollador recuerde agregar el filtro en cada query es insuficiente; se requiere una garantía estructural.

## Consecuencias

- Toda ruta nueva que accede a datos de negocio debe usar `TenantCollection`, no el driver de Mongo directamente.
- Toda ruta nueva requiere su test de aislamiento negativo (token de tenant A contra IDs de tenant B → 404, no 403, para no confirmar existencia).
- El router del portal de proveedores debe mantenerse físicamente separado del router de compradores — no debe existir código de ruta compartido que enumere vendors o evaluaciones ajenas.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 5.
- [`docs/security/threat-model.md`](../../security/threat-model.md).
