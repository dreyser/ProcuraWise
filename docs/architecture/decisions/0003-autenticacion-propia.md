# ADR 0003: Autenticación propia (authlib + OIDC directo + JWT propio)

**Estado:** Accepted
**Fecha:** 2026-07-15
**Origen:** Sesión de planeación arquitectónica

## Contexto

El flujo de invitación de proveedores (acceso vía token, sin cuenta previa, a una evaluación específica de un comprador) requiere código custom sin importar el proveedor de identidad (IdP) elegido para los compradores. Adicionalmente, un servicio de auth gestionado (Auth0, Clerk, etc.) tiene costo por usuario activo, indeseable mientras no hay ingresos.

## Decisión

Autenticación propia: `authlib` + OIDC directo a Microsoft/Google para compradores, JWT propio emitido por ProcuraWise, e invitación por token para proveedores (sin cuenta previa). Sin MFA (ver [ADR 0014](0014-mfa-excluido-conflicto-interes-eula.md)).

## Alternativas consideradas

- **Auth0/Clerk u otro IdP gestionado**: descartado — costo por usuario activo antes de tener ingresos, y el flujo de invitación de proveedor igual requeriría código custom encima.
- **Solo OIDC, sin password local**: descartado — no todos los compradores objetivo (México/LatAm, PyMEs) necesariamente tienen cuentas organizacionales de Microsoft/Google.

## Consecuencias

- ProcuraWise es responsable de la emisión, rotación y expiración de sus propios JWT — no se delega esa responsabilidad de seguridad a un tercero.
- El `tenant_id` como claim del JWT (ver [ADR 0002](0002-multi-tenant-mongodb.md)) depende de que esta emisión propia sea correcta y esté bien probada.
- MFA queda fuera del alcance de este mecanismo — no hay puntos de extensión activos preparados para él.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 5.
