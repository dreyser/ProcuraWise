import { useRef } from 'react'
import { useListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGet } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ErrorBanner'
import { formatFileSize } from '@/lib/formatFileSize'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { useDocumentActions } from '@/features/vendor-portal/hooks/useDocumentActions'
import type { DocumentListResponse } from '@/api/client'

interface RequirementEvidenceUploadProps {
  proposalId: string
  requirementId: string
  disabled: boolean
}

/** Per-requirement evidence slot (brief §11.1: `(proposal_id, requirement_id)`
 * with replace/version semantics) - a new upload here always supersedes the
 * current one, it never adds a second simultaneous file for the same
 * requirement (unlike ProposalDocumentsPanel's general attachments). Fetches
 * its own document list - React Query dedupes this against every other
 * instance's (and ProposalDocumentsPanel's) identical query. */
export function RequirementEvidenceUpload({
  proposalId,
  requirementId,
  disabled,
}: RequirementEvidenceUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const actions = useDocumentActions(proposalId)
  const listQuery = useListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGet(proposalId)
  const document = (unwrapData<DocumentListResponse>(listQuery.data)?.items ?? []).find(
    (d) => d.requirement_id === requirementId && d.status === 'current',
  )

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) actions.upload(file, requirementId)
  }

  return (
    <div className="mt-3 rounded-md border border-dashed border-border p-3">
      <p className="text-xs font-medium text-muted-foreground">Evidencia adjunta</p>

      {actions.uploadError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(actions.uploadError).message} />
        </div>
      )}
      {actions.deleteError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(actions.deleteError).message} />
        </div>
      )}
      {Boolean(actions.downloadError) && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(actions.downloadError).message} />
        </div>
      )}

      {document ? (
        <div className="mt-2 flex items-center justify-between gap-3 text-sm">
          <div>
            <p className="font-medium text-foreground">{document.filename}</p>
            <p className="text-xs text-muted-foreground">
              {formatFileSize(document.size_bytes)} · v{document.version}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={actions.downloadingId === document.id}
              onClick={() => actions.download(document.id)}
            >
              Descargar
            </Button>
            {!disabled && (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={actions.isDeleting}
                onClick={() => actions.remove(document.id)}
              >
                Eliminar
              </Button>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">Sin evidencia adjunta.</p>
      )}

      {!disabled && (
        <div className="mt-2">
          <input
            ref={fileInputRef}
            type="file"
            className="sr-only"
            id={`requirement-evidence-upload-${requirementId}`}
            // Not "Adjuntar evidencia..."/"Reemplazar evidencia..." - a
            // native <input type="file"> has an implicit ARIA role of
            // "button", so an overlapping name would make this hidden
            // input match the same getByRole('button', {name: ...})
            // locator as the real, visible trigger Button below (found by
            // e2e/documents.spec.ts turning ambiguous after adding the
            // label axe-core required - Fase 26).
            aria-label="Selector de archivo para evidencia del requerimiento"
            onChange={handleFileChange}
            disabled={actions.isUploading}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={actions.isUploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {actions.isUploading
              ? 'Subiendo…'
              : document
                ? 'Reemplazar evidencia'
                : 'Adjuntar evidencia'}
          </Button>
        </div>
      )}
    </div>
  )
}
