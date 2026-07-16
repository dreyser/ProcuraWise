# ADR 0009: Rúbricas económicas (condiciones comerciales y riesgo/predictibilidad)

**Estado:** Accepted
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

La fórmula final de scoring (Funcional 40% / Técnico 20% / Económico 40%) requería que el componente económico se desglosara en criterios auditables, no en un puntaje libre subjetivo.

## Decisión

Dentro del 40% económico: TCO normalizado 70%; Condiciones comerciales 15% (pago/plazo 25%, protección de precio/incrementos 25%, flexibilidad contractual/consumo 20%, descuentos/créditos/incentivos 15%, transparencia/facturación 15%); Riesgo/predictibilidad 15% (exposición a costos variables 30%, incrementos/indexación/renovaciones 25%, supuestos/exclusiones/costos omitidos 20%, exposición cambiaria/fiscal/regulatoria 15%, salida/portabilidad/lock-in 10%). Escala humana 0-5 con guías por criterio; scores 0/1/2/5 requieren comentario; "N/A" requiere justificación. Criterios/pesos configurables antes de publicar (deben sumar 100%), congelados en snapshot al publicar.

## Alternativas consideradas

- **Puntaje comercial/riesgo libre sin sub-criterios**: descartado — demasiado subjetivo y no auditable, en contradicción con el requisito de trazabilidad del producto.
- **Pesos derivados automáticamente por IA**: descartado — viola el principio no negociable de human-in-the-loop para el scoring final.

## Consecuencias

- Todo evaluador que asigne un score extremo (0, 1, 2 o 5) debe justificarlo por escrito — la UI debe forzar este campo.
- Los pesos quedan congelados en el snapshot de publicación; cambiarlos después de publicar requiere el flujo de nueva versión (ver [ADR 0013](0013-versionado-propuestas-negociacion.md)), no una edición directa.

## Referencias

- Backlog, Fase 20.
