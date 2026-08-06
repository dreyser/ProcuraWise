import { useRef, useState } from 'react'
import {
  useConfirmImportApiV1EvaluationsEvaluationIdRequirementsImportConfirmPost,
  usePreviewImportApiV1EvaluationsEvaluationIdRequirementsImportPreviewPost,
  type RequirementCreateRequest,
  type RequirementImportPreviewResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ErrorBanner } from '@/components/ErrorBanner'
import { normalizeApiError } from '@/lib/errors'
import { unwrapDataOrThrow } from '@/lib/http'

interface ImportRequirementsDialogProps {
  evaluationId: string
  existingRequirementCountByDimension: Record<string, number>
  onImported: () => void
}

const TARGET_FIELDS: Array<{ key: string; label: string; required: boolean }> = [
  { key: 'dimension', label: 'Dimensión (functional/technical)', required: true },
  { key: 'category', label: 'Categoría', required: true },
  { key: 'title', label: 'Título', required: true },
  { key: 'description', label: 'Descripción', required: true },
  { key: 'priority', label: 'Prioridad (mandatory/important/desirable)', required: true },
  { key: 'response_type', label: 'Tipo de respuesta (por defecto: texto)', required: false },
  { key: 'weight', label: 'Peso', required: true },
  { key: 'required', label: 'Obligatorio', required: false },
  { key: 'buyer_guidance', label: 'Guía para el proveedor', required: false },
]

const UNMAPPED = '__unmapped__'
const TRUTHY_VALUES = new Set(['true', '1', 'si', 'sí', 'yes', 'x'])

function toRequirement(
  row: Record<string, unknown>,
  mapping: Record<string, string>,
  displayOrder: number,
): RequirementCreateRequest | null {
  const cell = (field: string): string => {
    const column = mapping[field]
    if (!column) return ''
    const value = row[column]
    return value === null || value === undefined ? '' : String(value).trim()
  }
  const title = cell('title')
  const dimension = cell('dimension')
  if (!title || !dimension) return null
  const weight = Number(cell('weight'))
  return {
    dimension: dimension as RequirementCreateRequest['dimension'],
    category: cell('category'),
    title,
    description: cell('description'),
    priority: cell('priority') as RequirementCreateRequest['priority'],
    response_type: (cell('response_type') || 'text') as RequirementCreateRequest['response_type'],
    weight: Number.isFinite(weight) ? weight : 0,
    required: TRUTHY_VALUES.has(cell('required').toLowerCase()),
    display_order: displayOrder,
    buyer_guidance: cell('buyer_guidance') || null,
  }
}

/** Fase 23 (backlog fila 23: "import Excel/CSV con preview+mapeo"). Column
 * mapping only - the backend's RequirementImportPreview shape carries a
 * per-column `suggested_mapping`, not per-row value remapping, so this
 * dialog lets the user re-point columns (not edit cell values); malformed
 * enum values (dimension/priority/response_type) surface as a 422 from the
 * confirm mutation, same as any other form on this page. Every row this
 * dialog produces flows through the same
 * EvaluationRepository.add_requirements_bulk write path as manual entry and
 * "aplicar plantilla" - the request/response schema is reused verbatim
 * (RequirementCreateRequest). */
export function ImportRequirementsDialog({
  evaluationId,
  existingRequirementCountByDimension,
  onImported,
}: ImportRequirementsDialogProps) {
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<RequirementImportPreviewResponse | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const fileInputRef = useRef<HTMLInputElement>(null)

  const previewImport = usePreviewImportApiV1EvaluationsEvaluationIdRequirementsImportPreviewPost({
    mutation: {
      onSuccess: (response) => {
        const data = unwrapDataOrThrow<RequirementImportPreviewResponse>(response)
        setPreview(data)
        setMapping(data.suggested_mapping)
      },
    },
  })
  const confirmImport = useConfirmImportApiV1EvaluationsEvaluationIdRequirementsImportConfirmPost({
    mutation: {
      onSuccess: () => {
        onImported()
        resetAndClose()
      },
    },
  })

  function resetAndClose() {
    setOpen(false)
    setPreview(null)
    setMapping({})
    previewImport.reset()
    confirmImport.reset()
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    previewImport.mutate({ evaluationId, data: { file: file as unknown as string } })
  }

  function handleConfirm() {
    if (!preview) return
    const counters = { ...existingRequirementCountByDimension }
    const requirements: RequirementCreateRequest[] = []
    for (const row of preview.rows) {
      const dimensionCell = mapping.dimension ? String(row[mapping.dimension] ?? '') : ''
      const nextOrder = (counters[dimensionCell] ?? 0) + 1
      const requirement = toRequirement(row, mapping, nextOrder)
      if (!requirement) continue
      counters[dimensionCell] = nextOrder
      requirements.push(requirement)
    }
    confirmImport.mutate({ evaluationId, data: { requirements } })
  }

  const mappedRequiredCount = TARGET_FIELDS.filter((f) => f.required && mapping[f.key]).length
  const canConfirm =
    preview !== null && mappedRequiredCount === TARGET_FIELDS.filter((f) => f.required).length

  return (
    <>
      <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
        Importar Excel/CSV
      </Button>

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) resetAndClose()
          else setOpen(true)
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Importar requerimientos</DialogTitle>
            <DialogDescription>
              Sube un archivo Excel (.xlsx) o CSV, ajusta el mapeo de columnas y confirma para crear
              los requerimientos.
            </DialogDescription>
          </DialogHeader>

          {preview === null && (
            <div className="flex flex-col gap-4">
              {previewImport.isError && (
                <ErrorBanner message={normalizeApiError(previewImport.error).message} />
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.csv"
                className="sr-only"
                id="requirements-import-file"
                onChange={handleFileChange}
                disabled={previewImport.isPending}
              />
              <Button
                type="button"
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={previewImport.isPending}
              >
                {previewImport.isPending ? 'Leyendo archivo…' : 'Elegir archivo'}
              </Button>
            </div>
          )}

          {preview !== null && (
            <div className="flex max-h-[60vh] flex-col gap-4 overflow-y-auto">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Mapeo de columnas</h3>
                <div className="mt-2 grid grid-cols-2 gap-3">
                  {TARGET_FIELDS.map((field) => (
                    <div key={field.key}>
                      <Label htmlFor={`import-map-${field.key}`}>
                        {field.label}
                        {field.required ? ' *' : ''}
                      </Label>
                      <Select
                        value={mapping[field.key] || UNMAPPED}
                        onValueChange={(value) =>
                          setMapping((prev) => ({
                            ...prev,
                            [field.key]: value === UNMAPPED ? '' : value,
                          }))
                        }
                      >
                        <SelectTrigger id={`import-map-${field.key}`} className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNMAPPED}>Sin mapear</SelectItem>
                          {preview.columns.map((column) => (
                            <SelectItem key={column} value={column}>
                              {column}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  Vista previa ({preview.rows.length} filas)
                </h3>
                <div className="mt-2 overflow-x-auto rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {preview.columns.map((column) => (
                          <TableHead key={column}>{column}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.rows.slice(0, 5).map((row, index) => (
                        <TableRow key={index}>
                          {preview.columns.map((column) => (
                            <TableCell key={column}>{String(row[column] ?? '')}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>

              {confirmImport.isError && (
                <ErrorBanner message={normalizeApiError(confirmImport.error).message} />
              )}
              {!canConfirm && (
                <p className="text-xs text-muted-foreground">
                  Mapea todas las columnas obligatorias (*) para continuar.
                </p>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={resetAndClose}>
              Cancelar
            </Button>
            {preview !== null && (
              <Button
                type="button"
                onClick={handleConfirm}
                disabled={!canConfirm || confirmImport.isPending}
              >
                {confirmImport.isPending ? 'Importando…' : 'Confirmar importación'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
