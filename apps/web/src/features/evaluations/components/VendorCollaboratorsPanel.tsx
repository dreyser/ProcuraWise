import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQueryClient } from '@tanstack/react-query'
import {
  getListCollaboratorsApiV1VendorOrganizationsVendorOrgIdCollaboratorsGetQueryKey,
  useInviteCollaboratorApiV1VendorOrganizationsVendorOrgIdCollaboratorsPost,
  useListCollaboratorsApiV1VendorOrganizationsVendorOrgIdCollaboratorsGet,
  useRevokeCollaboratorInvitationApiV1VendorOrganizationsVendorOrgIdCollaboratorsInvitationIdRevokePost,
  type CollaboratorListResponse,
  type VendorInvitationResponse,
} from '@/api/client'
import { unwrapData, unwrapDataOrThrow } from '@/lib/http'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { normalizeApiError } from '@/lib/errors'
import { InviteLinkNotice } from '@/features/evaluations/components/InviteLinkNotice'

const inviteCollaboratorSchema = z.object({
  contact_email: z.string().trim().min(1, 'El correo es obligatorio').email('Correo inválido'),
  contact_display_name: z.string().trim().min(1, 'El nombre es obligatorio'),
})

type InviteCollaboratorFormValues = z.infer<typeof inviteCollaboratorSchema>

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pendiente',
  accepted: 'Aceptada',
  revoked: 'Revocada',
}

/**
 * Fase 15: "colaboradores múltiples por proveedor" - same role as the
 * primary contact, same permissions, invited only by the comprador
 * (founder decision D1 of the planning session). Every collaborator
 * accepts NDA/conflict of interés individually (ADR 0014) - this panel only
 * manages the invitation lifecycle, not the acceptance itself.
 */
export function VendorCollaboratorsPanel({ vendorOrgId }: { vendorOrgId: string }) {
  const queryClient = useQueryClient()
  const [newInvite, setNewInvite] = useState<VendorInvitationResponse | null>(null)

  const collaboratorsQuery =
    useListCollaboratorsApiV1VendorOrganizationsVendorOrgIdCollaboratorsGet(vendorOrgId)
  const collaborators = unwrapData<CollaboratorListResponse>(collaboratorsQuery.data)?.items ?? []

  const invalidate = () => {
    queryClient.invalidateQueries({
      queryKey:
        getListCollaboratorsApiV1VendorOrganizationsVendorOrgIdCollaboratorsGetQueryKey(
          vendorOrgId,
        ),
    })
  }

  const inviteCollaborator =
    useInviteCollaboratorApiV1VendorOrganizationsVendorOrgIdCollaboratorsPost({
      mutation: {
        onSuccess: (response) => {
          setNewInvite(unwrapDataOrThrow<VendorInvitationResponse>(response))
          invalidate()
        },
      },
    })
  const revokeInvitation =
    useRevokeCollaboratorInvitationApiV1VendorOrganizationsVendorOrgIdCollaboratorsInvitationIdRevokePost(
      { mutation: { onSuccess: invalidate } },
    )

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteCollaboratorFormValues>({ resolver: zodResolver(inviteCollaboratorSchema) })

  const onSubmit = async (values: InviteCollaboratorFormValues) => {
    await inviteCollaborator.mutateAsync({ vendorOrgId, data: values })
    reset()
  }

  return (
    <div className="mt-3 rounded-md border border-border p-3">
      <h3 className="text-sm font-semibold text-foreground">Colaboradores del proveedor</h3>

      {newInvite && (
        <div className="mt-2">
          <InviteLinkNotice
            email={newInvite.email}
            inviteUrl={newInvite.invite_url}
            onDismiss={() => setNewInvite(null)}
          />
        </div>
      )}

      {collaboratorsQuery.isLoading && <LoadingState label="Cargando colaboradores…" />}
      {collaboratorsQuery.error && (
        <ErrorBanner message={normalizeApiError(collaboratorsQuery.error).message} />
      )}

      {collaborators.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {collaborators.map((collaborator) => (
            <li
              key={collaborator.invitation_id}
              className="flex items-center justify-between rounded-md bg-muted px-2 py-1 text-xs"
            >
              <span>
                {collaborator.email} · {STATUS_LABEL[collaborator.status] ?? collaborator.status}
              </span>
              {collaborator.status === 'pending' && (
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  disabled={revokeInvitation.isPending}
                  onClick={() =>
                    revokeInvitation.mutate({
                      vendorOrgId,
                      invitationId: collaborator.invitation_id,
                    })
                  }
                >
                  Revocar
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={handleSubmit(onSubmit)}
        noValidate
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={`collab-email-${vendorOrgId}`}>Correo</Label>
          <Input
            id={`collab-email-${vendorOrgId}`}
            type="email"
            className="h-8 w-56"
            aria-invalid={Boolean(errors.contact_email)}
            {...register('contact_email')}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`collab-name-${vendorOrgId}`}>Nombre</Label>
          <Input
            id={`collab-name-${vendorOrgId}`}
            className="h-8 w-48"
            aria-invalid={Boolean(errors.contact_display_name)}
            {...register('contact_display_name')}
          />
        </div>
        <Button type="submit" size="sm" disabled={isSubmitting}>
          {isSubmitting ? 'Invitando…' : 'Invitar colaborador'}
        </Button>
      </form>
      {(errors.contact_email || errors.contact_display_name) && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {errors.contact_email?.message ?? errors.contact_display_name?.message}
        </p>
      )}
      {inviteCollaborator.isError && (
        <div className="mt-2">
          <ErrorBanner message={normalizeApiError(inviteCollaborator.error).message} />
        </div>
      )}
    </div>
  )
}
