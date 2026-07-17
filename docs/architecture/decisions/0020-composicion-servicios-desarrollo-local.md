# ADR 0020: Composición de servicios de desarrollo local (cola por defecto: InMemoryMessageBus)

**Estado:** Accepted
**Fecha:** 2026-07-17
**Origen:** Sesión de planeación de Fase 1B

## Contexto

El diseño original (ADR 0005, `architecture.md` §4/§7/§9, `deployment.md`) asumía Redis como cola local de desarrollo y Mailhog como captura local de correo, ambos como parte del `docker-compose.yml` por defecto desde la Fase 0. Al planear la Fase 1B (infraestructura local ejecutable), el founder acotó el alcance: ningún job asíncrono real existe todavía (llega en la Fase 13), y no hay correo transaccional que capturar (llega en la Fase 24). Levantar Redis y Mailhog en esta fase añadiría infraestructura sin ningún consumidor real, contradiciendo la preferencia del proyecto por no construir mecanismo sin caso de uso concreto.

Esta decisión **no reabre** la elección de Azure Service Bus para staging/producción (ADR 0005) — solo cambia cuál es el backend por defecto en desarrollo **local**.

## Decisión

- El `docker-compose.yml` por defecto de desarrollo local incluye únicamente **MongoDB Community** y **Azurite** (Blob). No incluye Redis ni Mailhog.
- La aplicación usa `InMemoryMessageBus` como implementación por defecto de la interfaz `MessageBus` (`service/procurawise/shared/messaging.py`) en desarrollo local y en pruebas unitarias. Vive dentro del proceso, no requiere contenedor, y no es válida en producción — `Settings` rechaza `environment=production` con `queue_backend=memory` (ver `shared/config.py`).
- `InMemoryMessageBus` no asume que API y worker comparten memoria: cada proceso instancia la suya. No sustituye la necesidad futura de un backend real cross-proceso.
- Redis queda explícitamente fuera del alcance de esta fase — no se agrega ni siquiera como perfil opcional de `docker-compose.yml` mientras no exista un caso de uso concreto y aprobado. Reintroducirlo requiere justificación propia, no es un sustituto temporal de Azure Service Bus.
- El emulador oficial de Azure Service Bus se documenta en `docs/operations/deployment.md` como incorporación futura opcional, a agregar cuando exista el adaptador real de Service Bus (Fase 13+). No es requisito de `make dev`, `make test` ni `make dev-up`.
- Mailhog/Mailpit se difieren hasta que exista código de correo transaccional real que los consuma; la selección entre ambos se hace en esa fase, no ahora.

## Alternativas consideradas

- **Mantener Redis+Mailhog en el compose por defecto, sin uso real**: descartado — construye infraestructura sin consumidor, contradice la disciplina de no anticipar mecanismo sin caso de uso concreto.
- **Usar Redis como cola local aunque no haya jobs todavía**: descartado — el founder decidió explícitamente no usar Redis como sustituto temporal de Azure Service Bus; agregarlo requeriría su propia justificación futura.
- **Incluir el emulador de Azure Service Bus ahora, como perfil opcional**: descartado para esta fase — se documenta como incorporación futura, pero no se implementa hasta que exista el adaptador real que lo consuma.

## Consecuencias

- `docker-compose.yml`, `architecture.md` (§4, §7, §9) y `deployment.md` quedan alineados: el entorno local por defecto es Mongo + Azurite únicamente.
- `InMemoryMessageBus` debe implementar el `Protocol` `MessageBus` — el dominio y los casos de uso nunca dependen de la implementación concreta, permitiendo sustituirla por un adaptador de Azure Service Bus sin tocar lógica de negocio.
- La integración cross-proceso real entre API y worker (dispatch table de jobs) se prueba y se construye cuando exista el primer job asíncrono real y su adaptador correspondiente (Fase 13 en adelante) — no antes.
- ADR 0005 conserva su `Estado: Accepted` (la decisión de Service Bus en staging/producción sigue vigente); se le agrega una nota de referencia a este ADR para las partes relativas a Redis/Mailhog en desarrollo local, sin marcarlo `Superseded`.

## Referencias

- [ADR 0005 — Procesamiento asíncrono con worker y cola](0005-worker-asincrono-service-bus.md).
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md).
- [`docs/architecture/architecture.md`](../architecture.md), secciones 4, 7 y 9.
- [`docs/operations/deployment.md`](../../operations/deployment.md).
