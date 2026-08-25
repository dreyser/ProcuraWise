import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetCompanyProfileApiV1CompanyProfileGetQueryKey,
  useGetCompanyProfileApiV1CompanyProfileGet,
  useUpdateCompanyProfileApiV1CompanyProfilePut,
  type CompanyProfileResponse,
} from '@/api/client'
import { unwrapData } from '@/lib/http'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { normalizeApiError } from '@/lib/errors'

interface ProfileFields {
  legal_name: string
  tax_id: string
  address: string
  industry: string
  website_url: string
}

function fieldsFromProfile(profile: CompanyProfileResponse | undefined): ProfileFields {
  return {
    legal_name: profile?.legal_name ?? '',
    tax_id: profile?.tax_id ?? '',
    address: profile?.address ?? '',
    industry: profile?.industry ?? '',
    website_url: profile?.website_url ?? '',
  }
}

/** UAT-03 (R4): "Perfil de la empresa" - tenant_admin's second area
 * (alongside Facturación). Minimal identity only, per the founder's own
 * scope decision: legal_name/tax_id/address/industry plus website_url. The
 * URL is captured now specifically so a future, still-unbuilt research
 * feature can fetch/analyze the tenant's public site for requirement
 * drafting (backlog.md UAT-03) - that feature is out of scope here, and
 * whenever it is built it must go through ai.research_provider's
 * ResearchProvider Protocol and respect FoundryWebSearchProvider's legal
 * gate (CLAUDE.md S5.1, ADR 0011), never a direct fetch of this field from
 * a business module. */
export function CompanyProfilePage() {
  const queryClient = useQueryClient()
  const profileQuery = useGetCompanyProfileApiV1CompanyProfileGet()
  const profile = unwrapData<CompanyProfileResponse>(profileQuery.data)

  // Same "adjust state during render" idiom as EconomicAssessmentPanel.tsx
  // (avoids react-hooks/set-state-in-effect) - the form seeds itself from
  // the server response exactly once, then only local edits/the mutation's
  // own response ever change it.
  const [formState, setFormState] = useState<{ initialized: boolean; fields: ProfileFields }>({
    initialized: false,
    fields: fieldsFromProfile(undefined),
  })
  if (!formState.initialized && !profileQuery.isLoading && profile) {
    setFormState({ initialized: true, fields: fieldsFromProfile(profile) })
  }
  const fields = formState.fields
  const setField = (key: keyof ProfileFields, value: string) =>
    setFormState((prev) => ({ ...prev, fields: { ...prev.fields, [key]: value } }))

  const update = useUpdateCompanyProfileApiV1CompanyProfilePut({
    mutation: {
      onSuccess: (response) => {
        queryClient.setQueryData(getGetCompanyProfileApiV1CompanyProfileGetQueryKey(), response)
        const updated = unwrapData<CompanyProfileResponse>(response)
        setFormState({ initialized: true, fields: fieldsFromProfile(updated) })
      },
    },
  })

  if (profileQuery.isLoading) return <LoadingState label="Cargando perfil de la empresa…" />
  if (profileQuery.error) {
    return <ErrorBanner message={normalizeApiError(profileQuery.error).message} />
  }

  const handleSave = () => {
    update.mutate({ data: fields })
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-lg font-semibold text-foreground">Perfil de la empresa</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Datos básicos de tu organización, usados para identificarla en el sistema.
      </p>

      <div className="mt-6 flex flex-col gap-4">
        <div>
          <Label htmlFor="company-legal-name">Razón social</Label>
          <Input
            id="company-legal-name"
            value={fields.legal_name}
            onChange={(event) => setField('legal_name', event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="company-tax-id">RFC / identificador fiscal</Label>
          <Input
            id="company-tax-id"
            value={fields.tax_id}
            onChange={(event) => setField('tax_id', event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="company-address">Dirección</Label>
          <Input
            id="company-address"
            value={fields.address}
            onChange={(event) => setField('address', event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="company-industry">Industria</Label>
          <Input
            id="company-industry"
            value={fields.industry}
            onChange={(event) => setField('industry', event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="company-website-url">Sitio web</Label>
          <Input
            id="company-website-url"
            type="url"
            placeholder="https://ejemplo.com"
            value={fields.website_url}
            onChange={(event) => setField('website_url', event.target.value)}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Próximamente ProcuraWise podrá analizar tu sitio para sugerir requerimientos.
          </p>
        </div>

        {update.isError && <ErrorBanner message={normalizeApiError(update.error).message} />}

        <Button
          type="button"
          className="self-start"
          disabled={update.isPending}
          onClick={handleSave}
        >
          {update.isPending ? 'Guardando…' : 'Guardar'}
        </Button>
      </div>
    </div>
  )
}
