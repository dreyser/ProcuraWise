import { useState } from 'react'
import {
  useApplyKnowledgeTemplateApiV1EvaluationsEvaluationIdApplyKnowledgeTemplatePost,
  useListTemplatesApiV1KnowledgeTemplatesGet,
  type KnowledgeTemplateSummaryResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { normalizeApiError } from '@/lib/errors'

interface ApplyTemplateButtonProps {
  evaluationId: string
  onApplied: () => void
}

/** Fase 11: applies every item on a chosen KnowledgeTemplate to this draft
 * Evaluation in one action (founder decision: apply-all only, no per-item
 * selection - see plan §22.2). Shared between WizardStepRequirements (Step
 * 2) and RequirementsPage, mirroring how RequirementForm/WeightSummary are
 * already shared between those two surfaces. */
export function ApplyTemplateButton({ evaluationId, onApplied }: ApplyTemplateButtonProps) {
  const { data } = useListTemplatesApiV1KnowledgeTemplatesGet()
  const templates = unwrapData<{ items: KnowledgeTemplateSummaryResponse[] }>(data)?.items ?? []

  const [selectedTemplateId, setSelectedTemplateId] = useState('')

  const applyTemplate =
    useApplyKnowledgeTemplateApiV1EvaluationsEvaluationIdApplyKnowledgeTemplatePost({
      mutation: {
        onSuccess: () => {
          onApplied()
          setSelectedTemplateId('')
        },
      },
    })

  if (templates.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2">
      {applyTemplate.isError && (
        <div className="w-full">
          <ErrorBanner message={normalizeApiError(applyTemplate.error).message} />
        </div>
      )}
      <Label htmlFor="apply-template-select" className="sr-only">
        Plantilla
      </Label>
      <Select value={selectedTemplateId} onValueChange={setSelectedTemplateId}>
        <SelectTrigger id="apply-template-select" size="sm" className="w-64">
          <SelectValue placeholder="Aplicar una plantilla…" />
        </SelectTrigger>
        <SelectContent>
          {templates.map((template) => (
            <SelectItem key={template.id} value={template.id}>
              {template.name} ({template.item_count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={!selectedTemplateId || applyTemplate.isPending}
        onClick={() =>
          applyTemplate.mutate({
            evaluationId,
            data: { knowledge_template_id: selectedTemplateId },
          })
        }
      >
        {applyTemplate.isPending ? 'Aplicando…' : 'Aplicar plantilla'}
      </Button>
    </div>
  )
}
