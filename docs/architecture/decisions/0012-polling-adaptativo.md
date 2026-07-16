# ADR 0012: Polling adaptativo para operaciones asíncronas (no WebSockets/SSE/SignalR en el MVP)

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

Se necesitan actualizaciones de estado para operaciones largas (jobs de IA, reportes, imports) y pantallas colaborativas, sin la complejidad operativa de WebSockets/SSE/Azure SignalR en un MVP con 50 usuarios concurrentes como techo (NFR-003).

## Decisión

Toda operación larga responde `202 Accepted` con `{job_id, status_url}`; estados `queued|running|succeeded|failed|cancelled`. El frontend hace poll cada 15s (jobs) / 30s (pantallas colaborativas), se detiene en estado terminal, pausa si la pestaña no está visible, consulta de inmediato al recuperar foco, aplica backoff exponencial con jitter en error, respeta `Retry-After`, pausa offline y reanuda al reconectar, muestra advertencia pasados 15 min sin marcar el job como fallido, y siempre expone refresco manual + última hora de actualización. La API es la única fuente de verdad — una falla de polling nunca cambia el estado real del proceso.

## Alternativas consideradas

- **WebSockets/SSE/Azure SignalR**: descartado para el MVP — complejidad de infraestructura/operación no justificada a la escala de 50 usuarios concurrentes; se deja como punto de extensión abierto para una versión futura.
- **Sin actualizaciones en tiempo real, solo refresco manual**: descartado — mala UX para jobs de IA/reportes que pueden tardar minutos.

## Consecuencias

- Hay latencia perceptible en las actualizaciones (hasta el intervalo de polling) — aceptado como trade-off frente a la complejidad de tiempo real.
- Toda pantalla que dependa de un job asíncrono debe implementar el contrato completo (pausa en oculto, backoff, offline, advertencia a los 15 min) — no es opcional parcial.
- Migrar a SSE/WebSockets/SignalR en el futuro requiere un ADR nuevo que supere este.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), sección 4.
- Backlog, Fase 13 en adelante.
