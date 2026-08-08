# ADR 0024: Notificaciones reales vía Azure Communication Services (Email)

**Estado:** Accepted
**Fecha:** 2026-08-06
**Origen:** Sesión de planeación de Fase 24

## Contexto

`backlog.md` (Fase 24, E11) exige "Notificaciones reales (Azure Communication Services) + centro in-app", con criterio de aceptación "Notificación real enviada en al menos un evento clave (invitación, publicación)". El proveedor (Azure Communication Services) ya viene decidido por el propio texto del backlog y por `mvp-scope.md`/`deployment.md` — a diferencia de ADR 0023, esta sesión no evaluó proveedores alternativos de email transaccional (SendGrid, Twilio, etc.), ya que el nombre del proveedor está fijado por el backlog desde el diseño original del MVP.

`ADR 0020` dejó explícitamente abierta la elección entre Mailhog y Mailpit como captura local de correo, "hasta que exista código de correo transaccional real que los consuma" — esta sesión resuelve esa apertura.

No existe ningún emulador local de Azure Communication Services (a diferencia de Azurite para Blob Storage o el emulador de Service Bus ya usado en el proyecto).

## Decisión

- **`azure-communication-email`** (SDK oficial de Azure Communication Services para envío de correo) es la única dependencia nueva. Puramente Python, sin paquetes de sistema adicionales.
- Único archivo autorizado a importarlo: `service/procurawise/notifications/azure_acs_email_provider.py` — mismo principio de frontera que CLAUDE.md §5.1 ya exige para proveedores de IA, extendido aquí a un segundo SDK de proveedor externo. El resto de la aplicación depende únicamente del Protocol `NotificationEmailProvider` (`notifications/provider.py`).
- **Sin Mailhog ni Mailpit** — se cierra la apertura de ADR 0020 sin agregar ninguno de los dos: no existe emulador de ACS contra el cual cualquiera de las dos herramientas probaría algo significativo. El sustituto local/CI es `LoggingNotificationEmailProvider` (`notifications/provider.py`), que loguea el mensaje completo en vez de enviarlo y nunca lanza — usado automáticamente cuando `notifications_email_enabled=False` (default fuera de producción) o cuando la configuración real de ACS falla al resolverse. `make test-integration` (el mismo target Docker genérico que ya cubre el resto del backend — a diferencia de IA, que necesita el perfil `servicebus` aparte, `notifications/` no requiere infraestructura adicional) verifica el ciclo completo contra este provider, asertando sobre el log estructurado capturado.
- Validador de precondiciones **solo-producción** (`_require_real_notification_config_in_production`, mismo patrón que `_require_real_ai_config_in_production`), no fail-closed-en-todo-ambiente (patrón `foundry_web_search_enabled`) — no existe un gate legal documentado equivalente al de Foundry/Bing Grounding (ADR 0011) que justifique exigir credenciales de ACS en todo ambiente de desarrollo/CI para una función que ningún flujo local puede probar contra un servicio real de todos modos.

## Alternativas consideradas

- **SendGrid/Twilio/otro proveedor de email transaccional**: no evaluadas — el backlog ya nombra explícitamente "Azure Communication Services" como parte del criterio de la fase, sin dejar una elección de proveedor abierta como sí lo hizo Fase 23 con las librerías de generación de documentos.
- **Agregar Mailhog o Mailpit como captura local**: descartada — ninguna de las dos herramientas emula el wire protocol de ACS (a diferencia de Azurite, que sí emula fielmente Blob Storage), por lo que agregar cualquiera de las dos solo sumaría un contenedor más sin aumentar la confianza real de las pruebas locales.
- **Fail-closed en todo ambiente para la configuración de ACS**: descartada — forzaría credenciales reales en cada `.env` de desarrollo y en CI para una función que, a diferencia de Azure OpenAI (que sí tiene una API real accesible con una key de prueba), no tiene ningún endpoint de prueba/sandbox público equivalente a un costo/fricción razonable para desarrollo local.

## Consecuencias

- `service/pyproject.toml` gana `azure-communication-email` como dependencia nueva; `mypy` requiere `ignore_missing_imports` para `azure.communication.email.*`.
- El módulo `notifications/` se convierte en el único punto de la aplicación que importa este SDK, mismo patrón de frontera que `ai/` (proveedores de IA) y `reports/` (librerías de generación de documentos) ya establecieron.
- Ningún flujo de desarrollo/CI depende de que ACS esté configurado — `LoggingNotificationEmailProvider` garantiza que cada invitación/publicación/etc. sigue generando su fila in-app y su intento de envío (logueado), incluso sin credenciales reales.
- Cierra formalmente la apertura de ADR 0020 (Mailhog vs. Mailpit) — ningún contenedor de captura de correo se agrega a `docker-compose.yml`.

## Referencias

- [ADR 0005 — Procesamiento asíncrono con worker y cola](0005-worker-asincrono-service-bus.md)
- [ADR 0011 — Gate de research provider (aprobación legal Foundry)](0011-research-provider-gate-legal-foundry.md)
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md)
- [ADR 0016 — Retención de datos](0016-retencion-datos-1-anio.md)
- [ADR 0020 — Composición de servicios de desarrollo local](0020-composicion-servicios-desarrollo-local.md)
- [ADR 0021 — Abstracción de proveedor de IA](0021-ai-provider-abstraction.md)
- Backlog, Fase 24.
