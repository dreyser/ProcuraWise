import { useRef } from 'react'
import { useListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGet } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { formatFileSize } from '@/lib/formatFileSize'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData } from '@/lib/http'
import { useDocumentActions } from '@/features/vendor-portal/hooks/useDocumentActions'
import type { DocumentListResponse } from '@/api/client'

interface ProposalDocumentsPanelProps {
  proposalId: string
  disabled: boolean
}

/** General, proposal-level attachments (requirement_id=null) - a vendor may
 * add several simultaneously, none replaces another (brief §11.1: only a
 * requirement-scoped slot has replace/version semantics, see
 * RequirementEvidenceUpload). Fetches its own document list - React Query
 * dedupes this against RequirementEvidenceUpload's identical query, so the
 * list is still only ever fetched once per proposal view. */
export function ProposalDocumentsPanel({ proposalId, disabled }: ProposalDocumentsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const actions = useDocumentActions(proposalId)
  const listQuery = useListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGet(proposalId)
  const documents = unwrapData<DocumentListResponse>(listQuery.data)?.items ?? []
  const generalDocuments = documents.filter(
    (d) => d.requirement_id === null && d.status === 'current',
  )

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) actions.upload(file)
  }

  return (
    <div className="rounded-md border border-border p-4">
      <h2 className="text-sm font-semibold text-foreground">Documentos adjuntos</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Evidencia general de tu propuesta, no ligada a un requerimiento específico.
      </p>

      {actions.uploadError && (
        <div className="mt-3">
          <ErrorBanner message={normalizeApiError(actions.uploadError).message} />
        </div>
      )}
      {actions.deleteError && (
        <div className="mt-3">
          <ErrorBanner message={normalizeApiError(actions.deleteError).message} />
        </div>
      )}
      {Boolean(actions.downloadError) && (
        <div className="mt-3">
          <ErrorBanner message={normalizeApiError(actions.downloadError).message} />
        </div>
      )}

      <div className="mt-4">
        {listQuery.isLoading ? (
          <LoadingState label="Cargando documentos…" />
        ) : listQuery.error ? (
          <ErrorBanner message={normalizeApiError(listQuery.error).message} />
        ) : generalDocuments.length === 0 ? (
          <EmptyState
            title="Sin documentos"
            description="Aún no has adjuntado ningún documento general."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {generalDocuments.map((document) => (
              <li
                key={document.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
              >
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
              </li>
            ))}
          </ul>
        )}
      </div>

      {!disabled && (
        <div className="mt-4">
          <input
            ref={fileInputRef}
            type="file"
            className="sr-only"
            id="proposal-document-upload"
            // Not "Adjuntar documento..." - a native <input type="file">
            // has an implicit ARIA role of "button", so an overlapping
            // name would make this hidden input match the same
            // getByRole('button', {name: ...}) locator as the real,
            // visible trigger Button below (Fase 26, same issue as
            // RequirementEvidenceUpload.tsx).
            aria-label="Selector de archivo para documento de la propuesta"
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
            {actions.isUploading ? 'Subiendo…' : 'Adjuntar documento'}
          </Button>
        </div>
      )}
    </div>
  )
}
