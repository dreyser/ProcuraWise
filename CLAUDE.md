# CLAUDE.md — ProcuraWise

## 1. Visión del producto

SaaS B2B multi-tenant que convierte una necesidad de compra de software/tecnología en un proceso RFP riguroso, con IA que asiste pero nunca decide.

## 2. Fuente de verdad documental

Este archivo es operativo, no exhaustivo. Para todo lo demás:

| Duda sobre... | Consultar |
|---|---|
| El plan aprobado completo | [`docs/planning/approved-mvp-plan.md`](docs/planning/approved-mvp-plan.md) |
| Qué está dentro/fuera de alcance del MVP | [`docs/product/mvp-scope.md`](docs/product/mvp-scope.md) |
| Secuencia de bloques/fases | [`docs/product/roadmap.md`](docs/product/roadmap.md) |
| Nueva feature, historia, criterio de aceptación | [`docs/development/backlog.md`](docs/development/backlog.md) |
| Qué se está trabajando ahora mismo | [`docs/development/current-phase.md`](docs/development/current-phase.md) |
| Cierre/inicio de sesión | [`docs/development/session-handoff.md`](docs/development/session-handoff.md) |
| Duda arquitectónica | [`docs/architecture/architecture.md`](docs/architecture/architecture.md) y [`docs/architecture/decisions/`](docs/architecture/decisions/) |
| Seguridad, amenazas, riesgos aceptados | [`docs/security/threat-model.md`](docs/security/threat-model.md) |
| Despliegue, ambientes, infraestructura | [`docs/operations/deployment.md`](docs/operations/deployment.md) |

## 3. Arquitectura aprobada (no reabrir sin un ADR nuevo)

Monolito modular: un solo paquete Python `procurawise` (`service/`), entrypoints delgados para API síncrona (FastAPI) y worker asíncrono, sin lógica duplicada. Frontend React+TS como SPA independiente. MongoDB Atlas (tier M0 en el MVP). Azure Container Apps como hosting. Cola Redis local / Azure Service Bus en producción, con contrato de polling adaptativo (no WebSockets/SSE/SignalR en el MVP). Detalle completo en [`docs/architecture/architecture.md`](docs/architecture/architecture.md); cada decisión tiene su ADR en [`docs/architecture/decisions/`](docs/architecture/decisions/).

**Regla:** cualquier cambio a esta arquitectura (nuevo servicio, cambio de base de datos, cambio de patrón de comunicación, etc.) requiere un ADR nuevo antes de implementarse, no solo un comentario en el código.

## 4. Reglas multi-tenant no negociables

- Nunca confiar en un `tenant_id` enviado por el cliente (body/query/header) — siempre viene del claim del JWT.
- Todo acceso a datos de negocio pasa por el wrapper `TenantCollection`, nunca por el driver de Mongo directamente.
- Toda ruta nueva que toque datos de negocio requiere su test de aislamiento negativo (`tests/security/test_tenant_isolation.py` o `test_vendor_isolation.py`).
- El portal de proveedores (`/api/v1/vendor-portal/*`) y las rutas de `platform_admin` (`/api/v1/admin/*`) permanecen en routers físicamente separados de las rutas de comprador.

## 5. Reglas de seguridad

- Ninguna acción sensible se valida solo en frontend — siempre se revalida en backend.
- Ningún secreto se hardcodea en código ni se comitea al repositorio.
- `FoundryWebSearchProvider` permanece con su feature flag apagado por defecto; **nunca se activa sin aprobación legal documentada** (ver [ADR 0011](docs/architecture/decisions/0011-research-provider-gate-legal-foundry.md)).
- No implementar MFA — fue removido del proyecto, no es deuda técnica (ver [ADR 0014](docs/architecture/decisions/0014-mfa-excluido-conflicto-interes-eula.md)).

## 6. Reglas de calidad

- La calificación final de una propuesta siempre es humana — la IA sugiere, nunca decide ni auto-adjudica.
- `ruff`/`mypy`/`eslint` sin errores antes de comitear.
- No se salta el snapshot inmutable al publicar un RFP o al enviar una propuesta.

Before declaring a task complete:
- Run the relevant tests.
- Run linting and type checking when those tools exist.
- Add or update tests for changed behavior.
- Verify tenant isolation when applicable.
- Report commands executed and their results.

## 7. Definición de "hecho" por fase

Código + tests correspondientes (unit/integration, y de aislamiento si toca datos de negocio) + [`docs/development/current-phase.md`](docs/development/current-phase.md) y [`docs/development/session-handoff.md`](docs/development/session-handoff.md) actualizados + lint/typecheck verde + demo manual verificada contra el criterio de aceptación de la fase en [`docs/development/backlog.md`](docs/development/backlog.md).

## 8. Prohibiciones explícitas

- No dividir el monolito en microservicios sin un ADR nuevo.
- No agregar dependencias pesadas sin un ADR.
- No hardcodear secretos.
- No saltarse el snapshot inmutable en publicación de RFP o envío de propuesta.
- No activar `FoundryWebSearchProvider` sin aprobación legal documentada.
- No implementar MFA.
- No implementar adjudicación automática — la decisión final siempre requiere aprobación humana explícita.

## 9. Interfaz de comandos objetivo — pendiente de implementarse durante la fase de fundación

Los siguientes comandos son el objetivo de la Fase 0 (Bootstrap), **no existen todavía**:

```
make dev         # levanta api + web en local
make test        # corre unit + integration
make lint        # ruff + mypy + eslint + prettier
make typecheck   # mypy + tsc --noEmit
make contracts   # regenera tipos TS desde openapi.json vía orval
make migrate     # aplica migraciones de Mongo pendientes
```

**Antes de ejecutar cualquiera de estos comandos, verifica primero que exista `Makefile` y el target correspondiente.** Si no existen, no asumas que están implementados — repórtalo y, si la tarea lo requiere, créalos como parte del alcance de la Fase 0.

## 10. Regla de continuidad entre sesiones

Al cerrar cualquier sesión de trabajo en código (Fase 0 en adelante), actualiza [`docs/development/current-phase.md`](docs/development/current-phase.md) y añade una entrada en [`docs/development/session-handoff.md`](docs/development/session-handoff.md). Es el único mecanismo de continuidad entre sesiones sin memoria compartida.
