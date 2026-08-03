import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getDownloadUrlApiV1VendorPortalProposalsProposalIdDocumentsDocumentIdDownloadUrlGet,
  getListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGetQueryKey,
  useDeleteDocumentApiV1VendorPortalProposalsProposalIdDocumentsDocumentIdDelete,
  useUploadDocumentApiV1VendorPortalProposalsProposalIdDocumentsPost,
  type DocumentDownloadUrlResponse,
} from '@/api/client'
import { unwrapDataOrThrow } from '@/lib/http'

/** Shared upload/delete/download actions for a proposal's evidence -
 * ProposalDocumentsPanel (general attachments) and every per-requirement
 * RequirementEvidenceUpload instance each get their own hook instance, all
 * invalidating the same document-list query on success so every view of the
 * list (general panel + every requirement's own upload widget) stays in
 * sync without prop-drilling a shared mutation. */
export function useDocumentActions(proposalId: string) {
  const queryClient = useQueryClient()
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<unknown>(null)

  const invalidateList = () =>
    queryClient.invalidateQueries({
      queryKey:
        getListDocumentsApiV1VendorPortalProposalsProposalIdDocumentsGetQueryKey(proposalId),
    })

  const uploadMutation = useUploadDocumentApiV1VendorPortalProposalsProposalIdDocumentsPost({
    mutation: { onSuccess: invalidateList },
  })
  const deleteMutation =
    useDeleteDocumentApiV1VendorPortalProposalsProposalIdDocumentsDocumentIdDelete({
      mutation: { onSuccess: invalidateList },
    })

  const upload = (file: File, requirementId?: string) =>
    uploadMutation.mutate({
      proposalId,
      // The generated type is `file: string` - FastAPI's OpenAPI 3.1 output
      // describes UploadFile as `{type: string, contentMediaType: ...}`,
      // which orval's binary detection (still 3.0's `format: binary`
      // convention) doesn't recognize, so it falls back to `string`. The
      // runtime call (client.ts) does the right thing regardless
      // (`formData.append('file', value)` with whatever value is passed).
      data: { file: file as unknown as string, requirement_id: requirementId ?? null },
    })

  const remove = (documentId: string) => deleteMutation.mutate({ proposalId, documentId })

  /** On-demand only (brief §11.9/§I) - never pre-fetched on page load, a
   * fresh, re-authorized URL is requested at the moment the user clicks
   * "Descargar", each time. */
  const download = async (documentId: string) => {
    setDownloadError(null)
    setDownloadingId(documentId)
    try {
      const response =
        await getDownloadUrlApiV1VendorPortalProposalsProposalIdDocumentsDocumentIdDownloadUrlGet(
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

  return {
    upload,
    remove,
    download,
    isUploading: uploadMutation.isPending,
    isDeleting: deleteMutation.isPending,
    uploadError: uploadMutation.error,
    deleteError: deleteMutation.error,
    downloadError,
    downloadingId,
  }
}
