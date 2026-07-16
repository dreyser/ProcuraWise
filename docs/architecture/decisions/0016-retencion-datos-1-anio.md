# ADR 0016: Retención de datos — default 1 año post-cierre

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

Se necesita una política de retención de datos por defecto para evaluaciones cerradas, sin sobre-diseñar configurabilidad por tenant en el MVP.

## Decisión

Retención default de **1 año** posterior al cierre de la evaluación. Configurable por tenant queda como capacidad futura, no se construye en el MVP.

## Alternativas consideradas

- **Retención indefinida**: descartada — pasivo de datos innecesario, complica el derecho al olvido para proveedores UE (ver flag GDPR).
- **Retención configurable por tenant desde el día uno**: descartada — complejidad adicional no justificada antes de que exista un tenant real que lo haya solicitado.

## Consecuencias

- Se necesitará diseñar un job de purga/archivado antes de que los datos más antiguos del piloto alcancen la marca de 1 año — trabajo futuro rastreado, no bloqueante para el MVP.
- El flag de GDPR (proveedor basado en UE) puede requerir retención/derecho al olvido más estricto que este default — ver [`docs/security/threat-model.md`](../../security/threat-model.md).

## Referencias

- [`docs/product/mvp-scope.md`](../../product/mvp-scope.md).
