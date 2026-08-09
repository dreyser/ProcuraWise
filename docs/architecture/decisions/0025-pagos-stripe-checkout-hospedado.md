# ADR 0025: Pagos vía Stripe Checkout hospedado (compra única por-evaluación)

**Estado:** Accepted
**Fecha:** 2026-08-08
**Origen:** Sesión de planeación de Fase 25, resolución del founder al Bloqueante #1/#3

## Contexto

`backlog.md` (Fase 25, E11) exige "Billing/Admin básico P1: Stripe checkout, consola admin cross-tenant auditada", con criterio de aceptación "Cobro de prueba exitoso en modo sandbox; acción admin cross-tenant queda auditada con motivo". El proveedor (Stripe) ya viene fijado por el propio texto del backlog — igual que ADR 0024 con Azure Communication Services, esta sesión no evaluó procesadores alternativos.

`approved-mvp-plan.md` deja explícitamente abierto el modelo comercial ("por-evaluación o suscripción"). El founder resolvió esta pregunta bloqueante por compra única por-evaluación (`mode="payment"`), sin suscripción ni modelo híbrido en esta fase, dejando el diseño preparado para agregar suscripciones en una fase futura sin romper compatibilidad.

No existe ningún emulador local de Stripe (a diferencia de Azurite para Blob Storage o el emulador de Service Bus ya usado en el proyecto). El founder resolvió también que la verificación del criterio "cobro de prueba exitoso en modo sandbox" se cierra mediante una demostración manual en Stripe Test Mode, nunca contra CI.

## Decisión

- **`stripe`** (SDK oficial de Stripe) es la única dependencia nueva. Puramente Python, ship con `py.typed` (no requiere `ignore_missing_imports` en mypy, a diferencia de `reportlab`/`openpyxl`/`docx`/`azure-communication-email`).
- Único archivo autorizado a importarlo: `service/procurawise/billing/stripe_payment_provider.py` — mismo principio de frontera que CLAUDE.md §5.1 ya exige para proveedores de IA, extendido en Fase 24 a Azure Communication Services y aquí a un tercer SDK de proveedor externo. El resto de la aplicación depende únicamente del Protocol `PaymentProvider` (`billing/provider.py`).
- **Checkout hospedado por Stripe** (`stripe.checkout.Session`, `mode="payment"`), nunca Payment Intent/Elements embebido en el frontend de ProcuraWise. Ningún dato de tarjeta toca nunca el frontend ni el backend de ProcuraWise — el alcance PCI queda en **SAQ-A** (el nivel de auto-evaluación más bajo posible), ya que la totalidad de la captura de datos de pago ocurre en la página hospedada por Stripe. Consecuencia directa: **no se agrega `@stripe/stripe-js` ni ningún SDK de Stripe en el frontend** — un redirect simple a la `checkout_url` retornada por el backend es suficiente.
- **Compra única por-evaluación, sin suscripción, sin enforcement de entitlements** (Bloqueante #1, Opción A, resuelto por el founder). El pago se registra y audita, nunca bloquea ninguna acción del producto. El diseño (Protocol `PaymentProvider`, `BillingAccount` como ancla delgada de `stripe_customer_id`, sin campos de plan/límites) queda deliberadamente preparado para incorporar `mode="subscription"` en una fase futura reutilizando el mismo proveedor, el mismo webhook, la misma cuenta de billing — sin romper compatibilidad con lo construido en esta fase.
- **Precio resuelto 100% server-side**: el backend solo conoce un `stripe_price_id_evaluation` de configuración (un Price creado manualmente en el dashboard de Stripe); nunca calcula, recibe del cliente, ni hardcodea un monto o moneda. El monto/moneda de exhibición se lee de vuelta desde la respuesta de Stripe únicamente para mostrarlo, nunca para decidir nada.
- **Sin emulador local de Stripe** — el sustituto local/CI es `LocalPaymentProvider` (`billing/provider.py`), sin red, sin SDK, que responde instantáneamente y enruta el flujo completo a través de un simulador de checkout dev-only (`GET /billing/local-checkout/{session_id}`) que ejecuta exactamente el mismo código de negocio que el webhook real. Usado automáticamente cuando `billing_enabled=False` (default fuera de producción) o cuando la configuración real de Stripe falla al resolverse.
- **Verificación del criterio "cobro de prueba"**: en tres niveles (todo el código automatizado contra `LocalPaymentProvider`, sin red; creación real de Sesión en modo test vía el marcador opt-in `pytest -m stripe_sandbox`, nunca en CI; y una demostración manual real — Checkout hospedado completado con tarjeta de prueba + Stripe CLI reenviando el webhook — cuya evidencia se registra en `current-phase.md` al cerrar la fase). CI permanece 100% determinística, sin dependencia de red externa ni de una cuenta Stripe real.
- Validador de precondiciones **solo-producción** (`_require_real_billing_config_in_production`, mismo patrón que `_require_real_notification_config_in_production`), no fail-closed-en-todo-ambiente (patrón `foundry_web_search_enabled`) — no existe un gate legal documentado equivalente al de Foundry que justifique exigir credenciales de Stripe en todo ambiente de desarrollo/CI. Adicionalmente, un validador dedicado (`_reject_live_stripe_key_outside_production`) rechaza cualquier `stripe_secret_key` que no empiece con `sk_test_` fuera de `environment=production` — guarda barata contra una clave viva filtrada a un `.env` de desarrollo.

## Alternativas consideradas

- **Payment Intents / Stripe Elements embebido**: descartado — obligaría a que el frontend de ProcuraWise renderizara un formulario de tarjeta propio, ampliando el alcance PCI más allá de SAQ-A sin ningún beneficio de producto para el criterio de esta fase.
- **Suscripción (`mode="subscription"`) en esta fase**: descartada por decisión explícita del founder (Bloqueante #1) — exigiría decidir tiers/cadencia/comportamiento de cancelación, ninguno documentado, y al menos 5 tipos de evento de webhook adicionales frente a los 2 que este alcance requiere.
- **Otro procesador de pagos (Mercado Pago, Conekta, etc.)**: no evaluados — el backlog ya nombra explícitamente "Stripe" como parte del criterio de la fase, sin dejar una elección de proveedor abierta.
- **Fail-closed en todo ambiente para la configuración de Stripe**: descartada — forzaría credenciales reales en cada `.env` de desarrollo y en CI para una función que, a diferencia de Azure OpenAI (con endpoint de prueba real y accesible), no tiene ningún emulador local contra el cual probar de forma significativa.
- **Header `Idempotency-Key` propio de la API** (mencionado en la spec §17.1 como convención general): descartado para esta fase — el `idempotency_key` nativo de Stripe en la creación de Sesión, combinado con la regla de negocio de reutilizar una compra `pending` existente en vez de crear una segunda, cubre el mismo objetivo anti-doble-cobro sin construir middleware nuevo. Ningún otro endpoint del proyecto implementa hoy esa convención tampoco.

## Consecuencias

- `service/pyproject.toml` gana `stripe` como dependencia nueva; sin override de mypy necesario (el paquete ship con `py.typed`).
- El módulo `billing/` se convierte en el único punto de la aplicación que importa este SDK, mismo patrón de frontera que `ai/` (proveedores de IA) y `notifications/` (Azure Communication Services) ya establecieron.
- Ningún flujo de desarrollo/CI depende de que Stripe esté configurado — `LocalPaymentProvider` garantiza que el flujo completo de checkout sigue siendo demostrable y probable end-to-end, incluso sin credenciales reales.
- El founder debe provisionar una cuenta Stripe de prueba (API keys, un Product/Price, y el Webhook Secret) antes de que la demostración manual del Bloque 5 pueda ejecutarse — documentado en `docs/operations/deployment.md`.
- Agregar suscripciones en una fase futura reutiliza esta misma frontera (`PaymentProvider`, `BillingAccount.stripe_customer_id`) sin requerir un ADR de reemplazo, solo una extensión.

## Referencias

- [ADR 0005 — Procesamiento asíncrono con worker y cola](0005-worker-asincrono-service-bus.md)
- [ADR 0011 — Gate de research provider (aprobación legal Foundry)](0011-research-provider-gate-legal-foundry.md)
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md)
- [ADR 0020 — Composición de servicios de desarrollo local](0020-composicion-servicios-desarrollo-local.md)
- [ADR 0021 — Abstracción de proveedor de IA](0021-ai-provider-abstraction.md)
- [ADR 0024 — Notificaciones vía Azure Communication Services](0024-notificaciones-azure-communication-services.md)
- Backlog, Fase 25.
- Plan de Fase 25 (`~/.claude/plans/twinkling-shimmying-finch.md`, fuera del repo).
