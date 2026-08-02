# ADR 0011: Abstracción `ResearchProvider` + gate legal para Foundry Web Search

**Estado:** Accepted (para la abstracción `ResearchProvider` e `InternalKnowledgeProvider`/`CuratedSourceProvider`) / Proposed-Condicional (para la activación de `FoundryWebSearchProvider`)
**Fecha:** 2026-07-16
**Origen:** Sesión de planeación arquitectónica

## Contexto

La especificación (§9) ya recomendaba un "adaptador intercambiable" para búsqueda web. La revisión legal de qué datos pueden enviarse a un proveedor de búsqueda web externo (Microsoft Foundry Web Search) no está completa al momento de este plan, y FR-022 (§6.3) estaba originalmente marcado P0 dentro de un rango "todos P0".

## Decisión

Interfaz única `ResearchProvider` con tres implementaciones:
- **`InternalKnowledgeProvider`** (default obligatorio, biblioteca + documentos autorizados, sin red externa) — **P0, Accepted**.
- **`CuratedSourceProvider`** (lista administrada de URLs/fuentes aprobadas, sin búsqueda abierta, requiere aprobación de términos) — **Accepted**.
- **`FoundryWebSearchProvider`** (Microsoft Foundry Web Search real) — implementado pero **desactivado por defecto** vía feature flag por ambiente y luego por tenant, solo activable tras aprobación legal explícita; nunca fallback automático si falla (degrada a `InternalKnowledgeProvider` e lo indica en la UI) — **Proposed/Conditional**.

Gobernanza: Accountable = founder/Product Owner; Responsible = abogado externo; Consulted = responsable técnico + seguridad. La revisión inicia en paralelo a la Fase 1, conclusión preliminar antes de la Fase 7, aprobación final ≥2 semanas antes del piloto (Fase 28); se repite si cambia proveedor/términos/región/datos/arquitectura. Política de datos: nunca se envían datos personales, nombre del cliente, proveedores participantes, respuestas/precios/propuestas, documentos cargados, información contractual/confidencial ni secretos — solo consultas abstractas y sanitizadas por categoría.

Como consecuencia directa, **FR-022 queda reclasificado de P0 a P1 condicionado**, con aprobación explícita del founder (ver contradicción documentada en `docs/planning/approved-mvp-plan.md`, sección 5).

## Alternativas consideradas

- **No incluir ninguna abstracción de búsqueda web, solo `InternalKnowledgeProvider` hardcodeado**: descartado — la spec explícitamente pide un camino adaptable hacia búsqueda web futura (§9).
- **Activar `FoundryWebSearchProvider` por defecto desde el inicio**: descartado — sin aprobación legal, riesgo crítico de exposición de datos según §24 de la spec.

## Consecuencias

- Ningún criterio de aceptación del MVP depende de búsqueda web en vivo funcionando.
- El caso de uso "Generación" de IA (§9) se angosta en el MVP a "contexto+biblioteca→candidatos" si la aprobación legal no llega a tiempo — aceptado explícitamente por el founder.
- Activar el flag de `FoundryWebSearchProvider` sin aprobación legal documentada está explícitamente prohibido (ver [`CLAUDE.md`](../../../CLAUDE.md)).

## Clarificación (2026-08-01, Fase 14)

La Fase 14 implementó lo aprobado arriba. Esta sección documenta la implementación real (no una ampliación de la decisión) y tres hallazgos concretos que la sesión de planeación de Fase 14 identificó, resueltos por el founder antes de implementar.

**Mecanismo de flag implementado — solo a nivel de ambiente, no todavía por tenant.** El texto original de esta ADR describe activación "por ambiente y luego por tenant". La Fase 14 implementó únicamente el nivel de ambiente: `Settings.foundry_web_search_enabled` (default `false` en todo ambiente) + `Settings.foundry_legal_approval_reference` (referencia humana a la aprobación legal documentada, no la aprobación en sí) + endpoint + nombre de agente, todos exigidos simultáneamente por un validador fail-closed (`_require_foundry_preconditions_when_enabled`) que corre en **todo** ambiente, no solo producción — si el flag es `true` pero falta cualquiera de los otros tres valores, el proceso no arranca. La activación por tenant queda **deliberadamente diferida**: el roadmap no ubica la aprobación legal antes de "≥2 semanas antes del piloto" (Fase 28), y construir un modelo de consentimiento por tenant para una capacidad que no puede activarse legalmente hasta entonces se habría tratado de trabajo especulativo (decisión explícita del founder en la sesión de planeación de Fase 14). Si la activación por tenant se retoma más adelante, extiende esta ADR o amerita una nueva, según qué tan material sea el cambio en ese momento.

**API concreta de Foundry Web Search identificada.** Esta ADR nunca especificó qué capacidad exacta de Microsoft se usaría. Un research spike (Microsoft Learn, agosto 2026) durante la planeación de Fase 14 confirmó: la capacidad real es el tool `web_search` del **Foundry Agent Service**, expuesto vía la **Responses API** (`POST {project_endpoint}/openai/v1/responses`), que internamente usa "Grounding with Bing Search"/"Grounding with Bing Custom Search". No es una API de búsqueda pura — es una llamada mediada por un modelo (requiere un agente Foundry pre-provisionado con el tool adjunto), y las citas vienen como anotaciones `url_citation` en la respuesta (`output_items[].content[].annotations[]`). Autenticación: Bearer token de Entra ID (`azure-identity`, scope `https://ai.azure.com/.default`), **no** una API key estática como Azure OpenAI. **Hallazgo material para la revisión legal**: "Grounding with Bing Search"/"Grounding with Bing Custom Search" son *First Party Consumption Services* de Microsoft, **no cubiertos por el Data Protection Addendum**, y los datos enviados **salen del boundary de compliance/geografía de Azure** — el abogado externo (Responsible, según la gobernanza de esta ADR) debe evaluar esto explícitamente, no asumir que aplican las mismas garantías que a Azure OpenAI.

**Decisión de implementación — REST directo, sin SDK de agentes.** `FoundryWebSearchProvider` llama la Responses API vía `httpx` directo + `azure-identity` (solo para el token), en vez de los SDKs `azure-ai-projects`/`azure-ai-agents`. La provisión del agente/conexión Bing en el proyecto Foundry es un paso de infraestructura de una sola vez (documentado en `docs/operations/deployment.md`), no algo que el adaptador haga en runtime — el adaptador solo referencia un `agent_name` ya provisionado. Esto mantiene la huella de dependencias mínima (decisión del founder, sesión de planeación de Fase 14) mientras el flag permanece apagado.

**Trazabilidad de fuentes — catálogo inmutable por job.** Cada `ResearchSnippet` que produce cualquier implementación de `ResearchProvider` (incluida una futura activación de `FoundryWebSearchProvider`) se persiste, sin modificar, como `AIExecution.source_catalog` en el momento de la generación — nunca re-derivado de `curated_sources` (mutable) en una lectura posterior. `AIRequirementCandidate.sources` solo contiene `source_id`s; un id que no está en el catálogo de ese job se descarta (`ai.service._sanitize_candidate_sources`, validado al generar y de nuevo al aceptar). Una URL mostrada a un usuario siempre viene de ese catálogo persistido, nunca directamente de la salida del modelo — mitiga que un modelo comprometido o alucinando inyecte una URL arbitraria en la UI.

## Referencias

- Backlog, Fases 13-14.
- [`docs/product/mvp-scope.md`](../../product/mvp-scope.md).
- [`docs/security/threat-model.md`](../../security/threat-model.md) — fila `ai`/`ResearchProvider` (Fase 14) y riesgos aceptados temporalmente.
- [`docs/operations/deployment.md`](../../operations/deployment.md) — configuración y provisión de infraestructura pendiente.
