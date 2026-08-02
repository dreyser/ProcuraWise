import { useState } from 'react'
import {
  useAcceptRequirementSuggestionsApiV1EvaluationsEvaluationIdAiRequirementSuggestionsJobIdAcceptPost,
  useTriggerRequirementSuggestionsApiV1EvaluationsEvaluationIdAiRequirementSuggestionsPost,
  type TriggerSuggestionRequestDimension,
  type TriggerSuggestionResponse,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { Textarea } from '@/components/ui/textarea'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { normalizeApiError } from '@/lib/errors'
import { unwrapDataOrThrow } from '@/lib/http'
import { useAiSuggestionJobStatus } from '@/features/evaluations/hooks/useAiSuggestionJobStatus'

interface AiSuggestRequirementsDialogProps {
  evaluationId: string
  onAccepted: () => void
}

/** Fase 13 (ai, ADR 0021): AI proposes, a human reviews and explicitly
 * accepts - candidates never touch Evaluation.requirements until the accept
 * call below, mirroring how ApplyTemplateButton triggers a single explicit
 * action, but gated on a review step this one can never skip (founder
 * decision: ephemeral job output, no auto-apply). */
export function AiSuggestRequirementsDialog({
  evaluationId,
  onAccepted,
}: AiSuggestRequirementsDialogProps) {
  const [open, setOpen] = useState(false)
  const [dimension, setDimension] = useState<TriggerSuggestionRequestDimension>('functional')
  const [description, setDescription] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())

  const trigger =
    useTriggerRequirementSuggestionsApiV1EvaluationsEvaluationIdAiRequirementSuggestionsPost({
      mutation: {
        onSuccess: (response) => {
          setJobId(unwrapDataOrThrow<TriggerSuggestionResponse>(response).job_id)
          setSelectedIndices(new Set())
        },
      },
    })
  const accept =
    useAcceptRequirementSuggestionsApiV1EvaluationsEvaluationIdAiRequirementSuggestionsJobIdAcceptPost(
      {
        mutation: {
          onSuccess: () => {
            onAccepted()
            resetAndClose()
          },
        },
      },
    )

  const job = useAiSuggestionJobStatus(evaluationId, jobId)

  function resetAndClose() {
    setOpen(false)
    setJobId(null)
    setDescription('')
    setSelectedIndices(new Set())
    trigger.reset()
    accept.reset()
  }

  function toggleCandidate(index: number) {
    setSelectedIndices((current) => {
      const next = new Set(current)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  function handleSubmit() {
    trigger.mutate({ evaluationId, data: { dimension, description } })
  }

  function handleRetry() {
    setJobId(null)
    trigger.reset()
  }

  function handleAccept() {
    if (!jobId) return
    accept.mutate({
      evaluationId,
      jobId,
      data: { candidate_indices: Array.from(selectedIndices) },
    })
  }

  return (
    <>
      <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
        Sugerir con IA
      </Button>

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) resetAndClose()
          else setOpen(true)
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Sugerir requerimientos con IA</DialogTitle>
            <DialogDescription>
              La IA propone candidatos a partir de tu biblioteca interna y evaluaciones previas.
              Ningún requerimiento se agrega hasta que lo revises y aceptes explícitamente.
            </DialogDescription>
          </DialogHeader>

          {jobId === null && (
            <div className="flex flex-col gap-4">
              {trigger.isError && (
                <ErrorBanner message={normalizeApiError(trigger.error).message} />
              )}
              <div className="flex flex-col gap-2">
                <Label htmlFor="ai-suggest-dimension">Dimensión</Label>
                <Select
                  value={dimension}
                  onValueChange={(value) =>
                    setDimension(value as TriggerSuggestionRequestDimension)
                  }
                >
                  <SelectTrigger id="ai-suggest-dimension">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="functional">Funcional</SelectItem>
                    <SelectItem value="technical">Técnico</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ai-suggest-description">¿Qué necesitas comprar?</Label>
                <Textarea
                  id="ai-suggest-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Ej: una plataforma de reportes con dashboards configurables…"
                  rows={4}
                />
              </div>
            </div>
          )}

          {jobId !== null &&
            (job === null || job.status === 'polling' || job.status === 'paused') && (
              <LoadingState label="Generando sugerencias…" />
            )}

          {jobId !== null && job?.result?.status === 'failed' && (
            <div className="flex flex-col gap-3">
              <ErrorBanner message={job.result.error ?? 'La generación falló. Intenta de nuevo.'} />
            </div>
          )}

          {jobId !== null && job?.result?.status === 'succeeded' && (
            <div className="flex flex-col gap-3">
              {job.stale && (
                <ErrorBanner
                  variant="info"
                  message="Esto está tardando más de lo esperado, pero seguimos intentando."
                />
              )}
              {/* Fase 14 (ADR 0011): structured, provider-neutral degradation -
               * never the job's terminal `error` field, since the job still
               * succeeded. Only ever populated if a secondary research
               * source (curated/web) was unavailable - InternalKnowledgeProvider
               * failing is still a hard job failure handled by the `failed`
               * branch above. */}
              {(job.result.warnings ?? []).length > 0 && (
                <ErrorBanner
                  variant="info"
                  message="Algunas fuentes de investigación no estuvieron disponibles para esta consulta; se usaron únicamente las fuentes restantes."
                />
              )}
              {accept.isError && <ErrorBanner message={normalizeApiError(accept.error).message} />}
              {(job.result.candidates ?? []).length === 0 && (
                <p className="text-sm text-muted-foreground">
                  La IA no encontró candidatos para esta descripción.
                </p>
              )}
              <ul className="flex flex-col gap-3">
                {(job.result.candidates ?? []).map((candidate, index) => {
                  // Fase 14: citations are resolved only from this job's own
                  // immutable source_catalog snapshot - never from a live
                  // query, and never a URL taken directly from model output
                  // (candidate.sources only ever carries source_id references).
                  const citedSources = candidate.sources
                    .map((sourceId) =>
                      (job.result?.source_catalog ?? []).find((s) => s.source_id === sourceId),
                    )
                    .filter((snippet) => snippet !== undefined)

                  return (
                    <li
                      key={index}
                      className="flex items-start gap-3 rounded-md border border-border p-3"
                    >
                      <Checkbox
                        id={`ai-candidate-${index}`}
                        checked={selectedIndices.has(index)}
                        onCheckedChange={() => toggleCandidate(index)}
                      />
                      <Label htmlFor={`ai-candidate-${index}`} className="flex flex-col gap-1">
                        <span className="font-medium text-foreground">{candidate.title}</span>
                        <span className="text-sm text-muted-foreground">
                          {candidate.description}
                        </span>
                        <span className="text-xs text-muted-foreground italic">
                          {candidate.rationale}
                        </span>
                        {citedSources.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            Fuentes:{' '}
                            {citedSources.map((snippet, sourceIndex) => (
                              <span key={snippet.source_id}>
                                {sourceIndex > 0 && ', '}
                                {snippet.url ? (
                                  <a
                                    href={snippet.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="underline"
                                    onClick={(event) => event.stopPropagation()}
                                  >
                                    {snippet.title}
                                  </a>
                                ) : (
                                  snippet.title
                                )}
                              </span>
                            ))}
                          </span>
                        )}
                      </Label>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <DialogFooter>
            {jobId === null && (
              <>
                <Button type="button" variant="outline" onClick={resetAndClose}>
                  Cancelar
                </Button>
                <Button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!description.trim() || trigger.isPending}
                >
                  {trigger.isPending ? 'Enviando…' : 'Generar sugerencias'}
                </Button>
              </>
            )}
            {jobId !== null && job?.result?.status === 'failed' && (
              <>
                <Button type="button" variant="outline" onClick={resetAndClose}>
                  Cerrar
                </Button>
                <Button type="button" onClick={handleRetry}>
                  Reintentar
                </Button>
              </>
            )}
            {jobId !== null && job?.result?.status === 'succeeded' && (
              <>
                <Button type="button" variant="outline" onClick={resetAndClose}>
                  Cancelar
                </Button>
                <Button
                  type="button"
                  onClick={handleAccept}
                  disabled={selectedIndices.size === 0 || accept.isPending}
                >
                  {accept.isPending
                    ? 'Aceptando…'
                    : `Aceptar seleccionados (${selectedIndices.size})`}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
