# ADR 0005: Procesamiento asíncrono con worker y cola (Redis local / Azure Service Bus en producción)

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

> **Nota (2026-07-17):** el backend de cola por defecto en desarrollo **local** cambió de Redis a `InMemoryMessageBus` — ver [ADR 0020](0020-composicion-servicios-desarrollo-local.md). La decisión de Azure Service Bus para staging/producción descrita abajo no cambia.

## Contexto

Operaciones largas o costosas (generación de requerimientos por IA, evaluación asistida por IA, generación de reportes, imports de Excel/CSV) no deben bloquear la API síncrona ni degradar la experiencia de otros usuarios concurrentes.

## Decisión

Proceso worker separado que comparte el mismo código de dominio que la API (llama `service.py` directamente, nunca HTTP interno), con una dispatch table de jobs. Cola Redis en desarrollo local, Azure Service Bus en staging/producción, mismo contrato de job expuesto al cliente vía `202 Accepted` + polling adaptativo (ver [ADR 0012](0012-polling-adaptativo.md)).

## Alternativas consideradas

- **Framework de colas de terceros (p. ej. Celery)**: descartado — dependencia adicional no justificada para el alcance y volumen del MVP; una dispatch table simple es suficiente y más fácil de razonar para 1 desarrollador.
- **Manejo síncrono de operaciones largas (request bloqueante)**: descartado — bloquea conexiones y degrada la UX en generación de IA/reportes, que pueden tomar minutos.

## Consecuencias

- Existe una diferencia de infraestructura entre Redis (dev) y Service Bus (prod) que debe mitigarse manteniendo el mismo contrato/interfaz de cola en ambos casos — riesgo de paridad dev/prod a vigilar.
- Todo job debe ser reintentable de forma idempotente (probado explícitamente antes del piloto, Fase 26).
- El worker nunca duplica lógica de negocio de la API — cualquier divergencia detectada en revisión de código es un defecto, no una variante aceptable.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 4.
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md).
