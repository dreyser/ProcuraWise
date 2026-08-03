import { useState } from 'react'
import {
  getDownloadUrlAsBuyerApiV1EvaluationsEvaluationIdProposalsProposalIdDocumentsDocumentIdDownloadUrlGet,
  useListDocumentsAsBuyerApiV1EvaluationsEvaluationIdProposalsProposalIdDocumentsGet,
  type DocumentDownloadUrlResponse,
  type DocumentListResponse,
} from '@/api/client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { EmptyState } from '@/components/EmptyState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { formatFileSize } from '@/lib/formatFileSize'
import { normalizeApiError } from '@/lib/errors'
import { unwrapData, unwrapDataOrThrow } from '@/lib/http'

interface BuyerDocumentsListProps {
  evaluationId: string
  proposalId: string
}

/** Read-only evidence review for the buyer side (brief §12: BUYER_READ_ROLES
 * get GET-only access, never upload/delete - the backend router itself has
 * no POST/DELETE routes at all, this component simply never renders
 * controls for actions that don't exist). Shows every current document
 * (general + per-requirement) in one flat list - the buyer reviews evidence
 * as a whole alongside the snapshot, not requirement-by-requirement like the
 * vendor's own upload view. */
export function BuyerDocumentsList({ evaluationId, proposalId }: BuyerDocumentsListProps) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<unknown>(null)

  const listQuery =
    useListDocumentsAsBuyerApiV1EvaluationsEvaluationIdProposalsProposalIdDocumentsGet(
      evaluationId,
      proposalId,
    )
  const documents = (unwrapData<DocumentListResponse>(listQuery.data)?.items ?? []).filter(
    (d) => d.status === 'current',
  )

  const handleDownload = async (documentId: string) => {
    setDownloadError(null)
    setDownloadingId(documentId)
    try {
      const response =
        await getDownloadUrlAsBuyerApiV1EvaluationsEvaluationIdProposalsProposalIdDocumentsDocumentIdDownloadUrlGet(
          evaluationId,
          proposalId,
          documentId,
        )
      const { url } = unwrapDataOrThrow<DocumentDownloadUrlResponse>(response)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (error) {
      setDownloadError(error)
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold text-foreground">Documentos del proveedor</h2>

      {Boolean(downloadError) && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(downloadError).message} />
        </div>
      )}

      <div className="mt-2">
        {listQuery.isLoading ? (
          <LoadingState label="Cargando documentos…" />
        ) : listQuery.error ? (
          <ErrorBanner message={normalizeApiError(listQuery.error).message} />
        ) : documents.length === 0 ? (
          <EmptyState
            title="Sin documentos"
            description="El proveedor no adjuntó documentos a esta propuesta."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {documents.map((document) => (
              <li
                key={document.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium text-foreground">{document.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(document.size_bytes)} · v{document.version}
                    {document.requirement_id
                      ? ' · evidencia de requerimiento'
                      : ' · adjunto general'}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={downloadingId === document.id}
                  onClick={() => handleDownload(document.id)}
                >
                  Descargar
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
