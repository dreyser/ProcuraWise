# ADR 0021: Abstracción `AIProvider` + Azure OpenAI como primera implementación

**Estado:** Accepted
**Fecha:** 2026-08-01
**Origen:** Sesión de planeación de Fase 13

## Contexto

`backlog.md` (Fase 13, E5) nombra `AIProvider` y `AIExecution` como los artefactos a construir ("Adaptador `AIProvider` real (Azure OpenAI/Foundry) para Descubrimiento+Generación usando solo `InternalKnowledgeProvider`; salida validada por schema; `AIExecution` con costo/modelo/prompt-version"), pero ningún ADR existente los especifica formalmente — ADR 0011 cubre únicamente `ResearchProvider` (búsqueda/descubrimiento web), no la abstracción de llamadas a un modelo de lenguaje. Fase 13 es también la primera vez que el repositorio ejecuta una operación asíncrona real: `InMemoryMessageBus` no cruza el límite de proceso API↔worker (ver ADR 0020), y ni el adaptador real de Azure Service Bus ni el worker's dispatch table existen todavía — ambos ADRs ya señalan explícitamente que esa pieza "llega" en esta fase.

El founder resolvió tres decisiones bloqueantes en la sesión de planeación (2026-08-01):
1. Construir el adaptador real de Azure Service Bus + emulador local ahora, no un interino en el mismo proceso.
2. Los candidatos de requerimiento generados por IA son efímeros (viven solo en el resultado del job) hasta que un humano los acepta explícitamente — nunca se escriben como `Requirement` real sin esa acción.
3. Fase 13 registra costo/uso de IA solo con fines de observabilidad; el límite/cuota aplicado se difiere a la Fase 26 (Hardening).

## Decisión

**`AIProvider`**: interfaz `typing.Protocol` (mismo patrón que `shared.storage.BlobStorage`) con un único método de generación y un `ping()` de salud:

```python
class AIProvider(Protocol):
    def generate(self, request: AIRequest) -> AIResponse: ...
    def ping(self) -> bool: ...
```

Azure OpenAI (`AzureOpenAIProvider`, sobre el SDK oficial `openai`) es la primera y única implementación de Fase 13. Ningún servicio de dominio (`ai.service`, `evaluations.*`) depende de Azure OpenAI directamente — solo del Protocol. Agregar un segundo proveedor (OpenAI directo, Anthropic, un modelo local) requiere escribir una clase nueva contra `AIProvider`, no tocar lógica de negocio.

**`ResearchProvider`**: interfaz ya aprobada por ADR 0011, implementada por primera vez en esta fase. Único implementador activo: `InternalKnowledgeProvider` (consulta `KnowledgeTemplateRepository`/`EvaluationRepository`, ambos ya `tenant_id`-scoped vía `TenantCollection`; sin red externa). `CuratedSourceProvider`/`FoundryWebSearchProvider` quedan fuera de esta fase (Fase 14, gate legal de ADR 0011).

**`AIExecution`**: entidad persistida (colección `ai_executions`, `TenantCollection`-scoped) que registra cada job: proveedor, modelo, versión de prompt, uso de tokens, costo estimado, latencia, estado (`queued|running|succeeded|failed`) y los candidatos generados. Es el análogo directo de `AuditEvent` para acciones de IA — mismo TTL de retención (`expires_at`, 1 año, ADR 0016) — pero es su propia colección, no un `AuditEvent` (distintas necesidades de campo, distinto ciclo de vida de "candidatos pendientes de revisión").

**Salida efímera hasta aceptación humana**: `AIExecution.candidates` contiene los candidatos validados por schema, pero ningún `Requirement` real se crea hasta que el usuario llama a un endpoint de aceptación explícito, que reutiliza el mismo bulk-write atómico que `KnowledgeTemplateService.apply_to_evaluation` ya estableció. Esto hace literal la regla "la IA sugiere, nunca decide" (CLAUDE.md §6) para este caso de uso: no existe un estado intermedio donde un candidato de IA se vea como un requerimiento real sin que un humano haya actuado.

**Job asíncrono real**: se implementa `ServiceBusMessageBus` (sobre `azure-servicebus`) detrás del mismo `Protocol` `MessageBus` (`shared/messaging.py`), y el worker (`worker/main.py`) gana su primer dispatch table real, consumiendo el trabajo de generación y llamando directamente a `ai.service` (nunca HTTP interno, por ADR 0001). El emulador oficial de Azure Service Bus se agrega a `docker-compose.yml` como perfil opcional (`--profile servicebus`), no al set por defecto de `make dev-up` — mantiene la disciplina de ADR 0020 de no levantar infraestructura sin consumidor concreto en el arranque por defecto, aunque el consumidor ya exista.

**Política de datos enviados a Azure OpenAI**: el alcance de Fase 13 (generación/descubrimiento de requerimientos) solo pone en la ruta de datos contenido de plantillas (`KnowledgeTemplate`) y requerimientos ya autorados por el propio comprador — nunca respuestas de propuesta, precios, documentos de proveedor ni información protegida por NDA (esos flujos no tocan `ai/` en esta fase). Aun así, se aplica la misma disciplina de saneamiento que ADR 0011 exige para `FoundryWebSearchProvider`: el texto libre del usuario entra solo en el prompt de usuario, nunca en el de sistema, y el proveedor nunca recibe PII, nombre del cliente ni identidad de proveedores.

**Costo/uso**: cada `AIExecution` registra `token_usage`/`cost_estimate` con fines de observabilidad. No se implementa un límite duro por tenant en esta fase — riesgo aceptado temporalmente, documentado en `threat-model.md`, revisado en la Fase 26.

## Alternativas consideradas

- **No formalizar `AIProvider` en un ADR, tratarlo como detalle de implementación**: descartado — CLAUDE.md §3 exige un ADR para cualquier cambio que introduzca un nuevo servicio externo o patrón de comunicación, y no existe ninguno que cubra específicamente la integración con un proveedor de LLM.
- **Interino en el mismo proceso para el job asíncrono (sin Service Bus real todavía)**: descartado por decisión explícita del founder — habría sido una segunda migración futura y no honra el "llega en la Fase 13" que ADR 0005/0020 ya dejaron escrito.
- **Escribir los candidatos de IA directamente como `Requirement` reales con un campo `review_status`**: descartado — el founder prefirió que nada con apariencia de requerimiento real exista antes de una acción humana explícita; también evita añadir campos nuevos al modelo `Requirement` compartido con `KnowledgeTemplate`.
- **Cuota/límite de costo duro desde ya**: descartado para esta fase — el founder aceptó el riesgo documentado a la escala del MVP (≤50 usuarios concurrentes, NFR-003), revisándolo en la Fase 26 junto con el resto de rate limiting.

## Consecuencias

- `ai/` deja de ser un bounded context solo nombrado en `architecture.md` y se convierte en código real; `architecture.md` §7/§10 se actualiza para reflejarlo.
- Se agregan dos dependencias nuevas a `pyproject.toml`: `openai` (cliente Azure OpenAI oficial) y `azure-servicebus` — ninguna reabre arquitectura por sí misma (ejecutan decisiones ya aprobadas por ADR 0005/0011), pero quedan documentadas aquí en vez de agregarse silenciosamente.
- El worker dispatch table pasa de stub a real; cualquier defecto de paridad entre lo que el worker ejecuta y lo que la API haría síncronamente es, por precedente de ADR 0005, un defecto de código, no una variante aceptable.
- Un segundo proveedor de IA en el futuro (Fase 14 en adelante, u otro vendor) implementa `AIProvider`/`ResearchProvider` sin tocar `evaluations`, `knowledge_templates` ni ningún router de dominio.
- El riesgo de abuso de costo queda documentado como aceptado temporalmente en `threat-model.md`, con dueño (founder) y fecha de revisión (Fase 26).

## Addendum (2026-08-01, Fase 14)

`ResearchProvider` (§16 arriba, "implementada por primera vez en esta fase" — Fase 13) gana sus implementaciones restantes en la Fase 14: `CuratedSourceProvider` y `FoundryWebSearchProvider` (esta última implementada pero desactivada en todo ambiente — ver la clarificación de 2026-08-01 en [ADR 0011](0011-research-provider-gate-legal-foundry.md)), compuestas vía `ai.composite_research_provider.build_research_provider()`. Ningún servicio de dominio cambia — siguen dependiendo únicamente del Protocol `ResearchProvider`, exactamente como esta ADR ya preveía.

También en Fase 14: el audit de frontera de IA de esa sesión de planeación encontró que `shared/health.py` importaba `AzureOpenAIProvider` directamente (en vez de pasar por `resolve_ai_provider()`) para el chequeo `/health/ready` — la única desviación del principio "ningún módulo fuera de `ai/` importa un adaptador concreto" que esta ADR establece implícitamente. Corregido en la misma fase, antes de que CLAUDE.md declarara la regla no negociable (§5.1).

## Referencias

- [ADR 0001 — Monolito modular](0001-monolito-modular.md)
- [ADR 0005 — Procesamiento asíncrono con worker y cola](0005-worker-asincrono-service-bus.md)
- [ADR 0011 — Abstracción `ResearchProvider` + gate legal para Foundry Web Search](0011-research-provider-gate-legal-foundry.md)
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md)
- [ADR 0016 — Retención de datos](0016-retencion-datos-1-anio.md)
- [ADR 0020 — Composición de servicios de desarrollo local](0020-composicion-servicios-desarrollo-local.md)
- Backlog, Fase 13.
