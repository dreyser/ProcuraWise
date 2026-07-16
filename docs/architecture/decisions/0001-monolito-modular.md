# ADR 0001: Monolito modular (FastAPI + worker, un solo paquete Python)

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

ProcuraWise es construido por 1 desarrollador. La escala objetivo del MVP (100 empresas, 500 evaluaciones, 50 usuarios concurrentes globales — NFR-003) no justifica el costo operativo de microservicios. Se necesita, sin embargo, separar el proceso síncrono (API) del asíncrono (jobs largos: IA, reportes) sin duplicar lógica de dominio.

## Decisión

Monolito modular: un solo proyecto Python (`service/`), un solo `pyproject.toml`/entorno virtual. API (FastAPI) y worker son entrypoints delgados sobre el mismo paquete `procurawise`. Bounded contexts como subpaquetes autocontenidos (`identity`, `evaluations`, `vendors`, `proposals`, `qna`, `scoring`, `tco`, `decisions`, `documents`, `notifications`, `ai`, `billing`, `admin`, `audit`, `shared`), cada uno con `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `events.py`, `exceptions.py`. Regla de dependencia: `router.py` → `service.py` → `repository.py`, nunca al revés; el worker llama `service.py` directamente, sin HTTP interno.

## Alternativas consideradas

- **Microservicios por bounded context**: descartado — overhead operativo (despliegue, observabilidad, red interna) injustificable para 1 desarrollador y la escala objetivo.
- **Monolito modular con despliegue independiente por módulo**: descartado — no hay justificación de escala que amerite desacoplar el ciclo de despliegue de los módulos entre sí.

## Consecuencias

- Toda nueva funcionalidad debe respetar la regla de dependencia `router → service → repository`; violarla es un anti-patrón de "microservicio disfrazado" que esta decisión busca evitar explícitamente.
- El worker importa `service.py` directamente — cualquier lógica que dependa de contexto HTTP no puede vivir ahí.
- Reabrir esta decisión (p. ej. migrar a microservicios) requiere un ADR nuevo que la sustituya explícitamente.

## Referencias

- [`docs/architecture/architecture.md`](../architecture.md), secciones 1-3.
