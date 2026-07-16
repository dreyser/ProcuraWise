# ADR 0004: Bicep sobre Terraform para IaC

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica (recomendación de herramental adoptada como parte del plan aprobado)

## Contexto

Toda la infraestructura del MVP es Azure (Container Apps, Blob, Key Vault, Container Registry, Service Bus en producción). No hay requisito de portabilidad multi-cloud.

## Decisión

Bicep como herramienta de Infraestructura como Código, en vez de Terraform.

## Alternativas consideradas

- **Terraform**: descartado — requiere gestión de state remoto (backend, locking) sin beneficio real dado que no hay multi-cloud; Bicep tiene mejor integración nativa con `az cli` y Azure Container Apps.
- **Pulumi**: no evaluado a fondo — no hay justificación para introducir un runtime de lenguaje de propósito general adicional solo para IaC en un proyecto Azure-only.

## Consecuencias

- No se necesita gestionar un backend de state remoto.
- El equipo (1 desarrollador) concentra su conocimiento de IaC en una herramienta Azure-specific; si el proyecto necesitara multi-cloud en el futuro, esta decisión tendría que reabrirse con un ADR nuevo.
- Infra real vía Bicep solo se aprovisiona en la Fase 27 — no bloquea el desarrollo de los Bloques 0-5, que corre 100% local.

## Referencias

- [`docs/operations/deployment.md`](../../operations/deployment.md).
