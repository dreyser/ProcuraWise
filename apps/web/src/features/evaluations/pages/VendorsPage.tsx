import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey,
  getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey,
  useGetEvaluationApiV1EvaluationsEvaluationIdGet,
  useLinkVendorApiV1EvaluationsEvaluationIdVendorsPost,
  useListProposalsApiV1EvaluationsEvaluationIdProposalsGet,
  useListVendorOrganizationsApiV1VendorOrganizationsGet,
  useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost,
  useUnlinkVendorApiV1EvaluationsEvaluationIdVendorsVendorOrgIdDelete,
  type EvaluationDetailResponse,
  type ProposalSummaryResponse,
  type VendorOrganizationListResponse,
} from '@/api/client'
import { ApiError, unwrapData } from '@/lib/http'
import { useAuth } from '@/auth/AuthContext'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DisabledActionHint } from '@/components/DisabledActionHint'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { translateEvaluationStatus, translateProposalStatus } from '@/lib/enumLabels'
import { normalizeApiError } from '@/lib/errors'
import { EvaluationTabNav } from '@/features/evaluations/components/EvaluationTabNav'
import { VendorCatalogPicker } from '@/features/evaluations/components/VendorCatalogPicker'
import { startCollectionPreconditionReasons } from '@/features/evaluations/lib/evaluationReadiness'
import {
  APPROVAL_INVALIDATED_MESSAGE,
  useApprovalInvalidationNotice,
} from '@/features/evaluations/lib/useApprovalInvalidationNotice'

const MAX_LINKED_VENDORS = 6

export function VendorsPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const { actor } = useAuth()
  const isOwner = actor?.role === 'evaluation_owner'
  const queryClient = useQueryClient()

  const evaluationQuery = useGetEvaluationApiV1EvaluationsEvaluationIdGet(evaluationId!)
  const evaluation = unwrapData<EvaluationDetailResponse>(evaluationQuery.data)

  const proposalsQuery = useListProposalsApiV1EvaluationsEvaluationIdProposalsGet(evaluationId!)
  const proposals = unwrapData<ProposalSummaryResponse[]>(proposalsQuery.data) ?? []

  // Unfiltered, high-limit catalog page used only to resolve vendor names
  // for already-linked vendors - independent of the picker's own search box.
  const namesQuery = useListVendorOrganizationsApiV1VendorOrganizationsGet({ limit: 100 })
  const namesCatalog = unwrapData<VendorOrganizationListResponse>(namesQuery.data)
  const nameById = new Map((namesCatalog?.items ?? []).map((item) => [item.id, item.name]))

  const [pendingUnlink, setPendingUnlink] = useState<{ vendorOrgId: string; name: string } | null>(
    null,
  )
  const [linkingId, setLinkingId] = useState<string | null>(null)
  const [confirmStart, setConfirmStart] = useState(false)

  const invalidateLinks = () => {
    queryClient.invalidateQueries({
      queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
    })
    queryClient.invalidateQueries({
      queryKey: getListProposalsApiV1EvaluationsEvaluationIdProposalsGetQueryKey(evaluationId),
    })
  }

  const linkVendor = useLinkVendorApiV1EvaluationsEvaluationIdVendorsPost({
    mutation: { onSuccess: invalidateLinks },
  })
  const unlinkVendor = useUnlinkVendorApiV1EvaluationsEvaluationIdVendorsVendorOrgIdDelete({
    mutation: { onSuccess: invalidateLinks },
  })
  const startCollection = useStartCollectionApiV1EvaluationsEvaluationIdStartCollectionPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetEvaluationApiV1EvaluationsEvaluationIdGetQueryKey(evaluationId),
        })
        setConfirmStart(false)
      },
    },
  })

  const invalidationNotice = useApprovalInvalidationNotice(evaluation?.approval_status)

  if (evaluationQuery.isLoading) return <LoadingState label="Cargando proveedores…" />
  if (evaluationQuery.error instanceof ApiError && evaluationQuery.error.status === 404) {
    return <ErrorBanner message="Esta evaluación no está disponible." />
  }
  if (evaluationQuery.error) {
    return <ErrorBanner message={normalizeApiError(evaluationQuery.error).message} />
  }
  if (!evaluation) return null

  const canEdit = isOwner && evaluation.status === 'draft'
  const atCapacity = proposals.length >= MAX_LINKED_VENDORS
  const linkedVendorOrgIds = new Set(proposals.map((p) => p.vendor_org_id))

  const startPreconditionReasons = startCollectionPreconditionReasons(evaluation)
  const canStartCollection = canEdit && startPreconditionReasons.length === 0

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">{evaluation.name}</h1>
        <StatusBadge label={translateEvaluationStatus(evaluation.status)} />
      </div>
      <EvaluationTabNav evaluationId={evaluation.id} />

      {invalidationNotice.visible && (
        <div className="mt-4">
          <ErrorBanner
            variant="info"
            message={APPROVAL_INVALIDATED_MESSAGE}
            onDismiss={invalidationNotice.dismiss}
          />
        </div>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">
          Proveedores vinculados ({proposals.length} / {MAX_LINKED_VENDORS})
        </h2>

        {proposalsQuery.isLoading && <LoadingState label="Cargando proveedores vinculados…" />}
        {proposalsQuery.error && (
          <ErrorBanner message={normalizeApiError(proposalsQuery.error).message} />
        )}
        {!proposalsQuery.isLoading && proposals.length === 0 && (
          <div className="mt-2">
            <EmptyState title="Ningún proveedor vinculado todavía" />
          </div>
        )}
        {proposals.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Estado de la propuesta</TableHead>
                  {canEdit && <TableHead>Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((proposal) => {
                  const name = nameById.get(proposal.vendor_org_id) ?? 'Proveedor'
                  return (
                    <TableRow key={proposal.id}>
                      <TableCell>{name}</TableCell>
                      <TableCell>
                        <StatusBadge label={translateProposalStatus(proposal.status)} />
                      </TableCell>
                      {canEdit && (
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              setPendingUnlink({ vendorOrgId: proposal.vendor_org_id, name })
                            }
                          >
                            Desvincular
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {canEdit && (
        <section className="mt-6 max-w-lg">
          <h2 className="text-sm font-semibold text-foreground">Vincular proveedor</h2>
          {atCapacity ? (
            <p className="mt-2 text-sm text-muted-foreground">
              Ya alcanzaste el máximo de {MAX_LINKED_VENDORS} proveedores vinculados.
            </p>
          ) : (
            <div className="mt-2">
              {linkVendor.isError && (
                <div className="mb-2">
                  <ErrorBanner message={normalizeApiError(linkVendor.error).message} />
                </div>
              )}
              <VendorCatalogPicker
                excludedIds={linkedVendorOrgIds}
                isLinking={linkVendor.isPending}
                linkingId={linkingId}
                disabled={false}
                onSelect={(vendorOrgId) => {
                  setLinkingId(vendorOrgId)
                  linkVendor.mutate(
                    { evaluationId: evaluation.id, data: { vendor_org_id: vendorOrgId } },
                    { onSettled: () => setLinkingId(null) },
                  )
                }}
              />
            </div>
          )}
        </section>
      )}

      {isOwner && evaluation.status === 'draft' && (
        <section className="mt-8">
          <Button
            type="button"
            disabled={!canStartCollection}
            onClick={() => setConfirmStart(true)}
          >
            Iniciar recepción de propuestas
          </Button>
          <DisabledActionHint reasons={canStartCollection ? [] : startPreconditionReasons} />
        </section>
      )}

      <ConfirmDialog
        open={pendingUnlink !== null}
        onOpenChange={(open) => !open && setPendingUnlink(null)}
        title="Desvincular proveedor"
        description={`${pendingUnlink?.name ?? 'Este proveedor'} dejará de estar vinculado a la evaluación.`}
        confirmLabel="Desvincular"
        variant="destructive"
        isPending={unlinkVendor.isPending}
        onConfirm={() => {
          if (!pendingUnlink) return
          unlinkVendor.mutate(
            { evaluationId: evaluation.id, vendorOrgId: pendingUnlink.vendorOrgId },
            { onSuccess: () => setPendingUnlink(null) },
          )
        }}
      />

      <ConfirmDialog
        open={confirmStart}
        onOpenChange={setConfirmStart}
        title="Iniciar recepción de propuestas"
        description="Los requerimientos y proveedores quedarán en modo de solo lectura. Los proveedores vinculados podrán empezar a responder."
        confirmLabel="Iniciar recepción"
        isPending={startCollection.isPending}
        onConfirm={() => startCollection.mutate({ evaluationId: evaluation.id })}
      />
      {startCollection.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(startCollection.error).message} />
        </div>
      )}
    </div>
  )
}
