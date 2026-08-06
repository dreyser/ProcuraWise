# ADR 0023: Generación de reportes — `reportlab` (PDF), `openpyxl` (XLSX), `python-docx` (DOCX)

**Estado:** Accepted
**Fecha:** 2026-08-06
**Origen:** Sesión de planeación de Fase 23

## Contexto

`backlog.md` (Fase 23, E10) exige generar los 8 entregables de la spec §10 ("Documento formal de RFP en Word y PDF. Matriz de requerimientos en Excel/CSV. Comparativo ejecutivo de proveedores. Reporte detallado de scoring y comentarios autorizados. Análisis de riesgos y excepciones. Tabla de TCO por año, categoría y proveedor. Acta/recomendación de adjudicación con aprobación. Resumen de preguntas y respuestas.") como jobs asíncronos que siguen el contrato de polling ya definido por ADR 0012. Ningún ADR previo cubre generación de documentos — `service/pyproject.toml` no tiene ninguna librería de PDF/Excel/Word (confirmado por auditoría de dependencias en la sesión de planeación). CLAUDE.md §8 prohíbe explícitamente agregar una dependencia pesada sin un ADR.

El founder resolvió la pregunta bloqueante única de la sesión de planeación de Fase 23 (2026-08-06): adoptar la Opción A completa (PDF+XLSX+DOCX, sin diferir ningún formato explícito de la spec).

## Decisión

Tres dependencias nuevas, todas puramente Python (sin paquetes de sistema/apt adicionales en `Dockerfile.api`/`Dockerfile.worker`, a diferencia de alternativas como WeasyPrint que requieren Pango/Cairo, o un navegador headless tipo Playwright/Puppeteer que además serían mucho más pesados en imagen/arranque/memoria para Azure Container Apps):

- **`reportlab`** (Platypus) para los 6 tipos de reporte narrativos/mixtos en PDF: `rfp_document`, `vendor_comparison`, `scoring_detail`, `risk_analysis`, `decision_record`, `qna_summary`. Maduro, con soporte nativo de tablas, encabezado/pie, numeración de página y paginación multi-sección — el ajuste correcto para documentos formales como el "Acta de decisión" o el "Documento formal de RFP".
- **`openpyxl`** para los 2 tipos tabulares en XLSX (`requirements_matrix`, `tco_breakdown`) — y reutilizado también para **leer** archivos `.xlsx` en la capacidad de import de la misma fase (una sola dependencia nueva cubre exportación e importación).
- **`python-docx`** (paquete pip `python-docx`, módulo `docx`) exclusivamente para el ítem 1 (`rfp_document`), que la spec exige explícitamente en "Word y PDF" — sin este ADR, el MVP habría tenido que diferir DOCX nativo a una fase futura.
- CSV (export e import) usa el módulo `csv` de la stdlib — sin dependencia nueva.

Ningún módulo de dominio (`evaluations`, `decisions`, `scoring`) importa `reportlab`/`openpyxl`/`docx` directamente — solo `reports/renderers/*.py`, mismo principio de frontera ya aplicado a `ai/` (CLAUDE.md §5.1) para proveedores externos, aplicado aquí a librerías de generación de documentos: el resto de la aplicación solo llama a `ReportService`, nunca a un renderer.

Protección contra CSV/formula injection (OWASP): toda celda de XLSX/CSV cuyo valor empiece con `=`, `+`, `-` o `@` se escapa con un prefijo de comilla simple antes de escribirse — aplicado uniformemente en `reports/renderers/{xlsx,csv}.py`, sin excepción por columna.

## Alternativas consideradas

- **WeasyPrint (HTML+CSS → PDF)**: descartada — requiere Pango/Cairo vía paquetes de sistema, incompatible con el objetivo de mantener las imágenes de `Dockerfile.api`/`Dockerfile.worker` mínimas y con el principio ya aplicado en Fase 14 de preferir REST directo sobre SDKs/dependencias pesadas cuando existe una alternativa más liviana.
- **Navegador headless (Playwright/Puppeteer) server-side**: descartada explícitamente por la propia guía de planeación de esta fase — cientos de MB de imagen adicional, arranque más lento, más RAM, mal ajuste para Azure Container Apps; Playwright ya es una dependencia de desarrollo del frontend (E2E), pero usarlo server-side en Python habría significado una dependencia de producción completamente nueva y mucho más pesada.
- **`fpdf2` en vez de `reportlab`**: descartada — API más simple pero con soporte de layout complejo (tablas multi-columna, TOC, encabezado/pie) más limitado; peor ajuste para el "Acta de decisión"/"Documento formal de RFP", que requieren estructura formal multi-sección.
- **Diferir DOCX nativo a una fase futura (Opción B de la sesión de planeación)**: descartada por decisión explícita del founder — `python-docx` es de bajo riesgo (pure-Python, misma familia OOXML que `openpyxl`) y permite cumplir literalmente el requisito de la spec sin recortar alcance.

## Consecuencias

- `service/pyproject.toml` gana tres dependencias nuevas: `reportlab`, `openpyxl`, `python-docx`. Ninguna reabre arquitectura por sí misma (ejecutan la decisión ya aprobada por ADR 0005/0012 de que "reportes" es un job asíncrono más), pero quedan documentadas aquí en vez de agregarse silenciamente.
- `mypy` requiere overrides de `ignore_missing_imports` para `reportlab.*`/`openpyxl.*`/`docx.*` (ninguna de las tres publica stubs completos) — configurado en `pyproject.toml`, sin relajar `disallow_untyped_defs` para el resto del proyecto.
- El módulo `reports/` se convierte en el único punto de la aplicación que importa estas tres librerías, mismo patrón de frontera que `ai/` ya estableció para proveedores externos.
- Un futuro noveno tipo de reporte, o un cambio de motor de renderizado, se agrega escribiendo un renderer nuevo contra la misma forma `assembly_data -> bytes`, sin tocar `reports/service.py` ni ningún módulo de dominio.

## Referencias

- [ADR 0005 — Procesamiento asíncrono con worker y cola](0005-worker-asincrono-service-bus.md)
- [ADR 0012 — Polling adaptativo](0012-polling-adaptativo.md)
- [ADR 0016 — Retención de datos](0016-retencion-datos-1-anio.md)
- Backlog, Fase 23.
