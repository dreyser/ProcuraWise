# ProcuraWise

SaaS B2B multi-tenant que convierte una necesidad de compra de software/tecnología en un proceso RFP riguroso, con IA que asiste pero nunca decide.

## Estado del proyecto

Greenfield. No hay código de aplicación, infraestructura ni dependencias instaladas todavía. Este repositorio contiene, por ahora, únicamente documentación de planeación, producto, arquitectura y seguridad. La implementación empieza en la Fase 0 (Bootstrap) — ver [`docs/development/current-phase.md`](docs/development/current-phase.md).

## Organización del repositorio

```
docs/
  requirements/   # especificación de producto original (fuente, no se edita)
  planning/       # plan aprobado del MVP (fuente de verdad de decisiones)
  product/        # alcance y roadmap
  development/    # backlog, fase actual, handoff entre sesiones
  architecture/    # arquitectura y ADRs (decisiones que no se reabren sin ADR nuevo)
  security/        # modelo de amenazas
  operations/      # despliegue e infraestructura
CLAUDE.md          # reglas operativas para trabajar en este repositorio
```

Cuando la implementación comience (Fase 0 en adelante), se añadirán `apps/web` (frontend React+TS), `service/` (backend Python monolito modular) e `infra/` (Bicep), según lo descrito en [`docs/architecture/architecture.md`](docs/architecture/architecture.md).

## Por dónde empezar

- **Para entender el producto:** [`docs/product/mvp-scope.md`](docs/product/mvp-scope.md).
- **Para entender la arquitectura:** [`docs/architecture/architecture.md`](docs/architecture/architecture.md) y [`docs/architecture/decisions/`](docs/architecture/decisions/).
- **Para saber qué se está trabajando ahora:** [`docs/development/current-phase.md`](docs/development/current-phase.md).
- **Reglas operativas para Claude Code:** [`CLAUDE.md`](CLAUDE.md).
