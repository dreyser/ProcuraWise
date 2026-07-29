import { type ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useActor } from '@/actor/ActorContext'
import { RequireActor, RequireRole } from '@/app/guards'
import { AppShell } from '@/app/AppShell'
import { roleHomePath } from '@/app/roleHomePath'
import { SelectActorPage } from '@/actor/SelectActorPage'
import { UnauthorizedPage } from '@/app/UnauthorizedPage'
import { NotFoundPage } from '@/app/NotFoundPage'
import { EvaluationListPage } from '@/features/evaluations/pages/EvaluationListPage'
import { EvaluationCreatePage } from '@/features/evaluations/pages/EvaluationCreatePage'
import { EvaluationDetailPage } from '@/features/evaluations/pages/EvaluationDetailPage'
import { RequirementsPage } from '@/features/evaluations/pages/RequirementsPage'
import { VendorsPage } from '@/features/evaluations/pages/VendorsPage'
import { ProposalsPage } from '@/features/proposals/pages/ProposalsPage'
import { ScoringPage } from '@/features/scoring/pages/ScoringPage'
import { ResultsPage } from '@/features/scoring/pages/ResultsPage'
import { VendorProposalListPage } from '@/features/vendor-portal/pages/VendorProposalListPage'
import { VendorProposalDetailPage } from '@/features/vendor-portal/pages/VendorProposalDetailPage'

const BUYER_ROLES = ['evaluation_owner', 'evaluator']
const VENDOR_ROLES = ['vendor_contact']

function BuyerLayout({ children }: { children: ReactElement }) {
  return (
    <RequireActor>
      <RequireRole roles={BUYER_ROLES}>
        <AppShell>{children}</AppShell>
      </RequireRole>
    </RequireActor>
  )
}

function VendorLayout({ children }: { children: ReactElement }) {
  return (
    <RequireActor>
      <RequireRole roles={VENDOR_ROLES}>
        <AppShell>{children}</AppShell>
      </RequireRole>
    </RequireActor>
  )
}

function RootRedirect() {
  const { actor, status } = useActor()
  if (status === 'loading') return null
  if (status === 'anonymous' || !actor) return <Navigate to="/dev/select-actor" replace />
  return <Navigate to={roleHomePath(actor.role)} replace />
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/dev/select-actor" element={<SelectActorPage />} />
        <Route path="/unauthorized" element={<UnauthorizedPage />} />

        <Route
          path="/evaluations"
          element={
            <BuyerLayout>
              <EvaluationListPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/new"
          element={
            <BuyerLayout>
              <EvaluationCreatePage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId"
          element={
            <BuyerLayout>
              <EvaluationDetailPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/requirements"
          element={
            <BuyerLayout>
              <RequirementsPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/vendors"
          element={
            <BuyerLayout>
              <VendorsPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/proposals"
          element={
            <BuyerLayout>
              <ProposalsPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/proposals/:proposalId/score"
          element={
            <BuyerLayout>
              <ScoringPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/results"
          element={
            <BuyerLayout>
              <ResultsPage />
            </BuyerLayout>
          }
        />

        <Route
          path="/vendor/proposals"
          element={
            <VendorLayout>
              <VendorProposalListPage />
            </VendorLayout>
          }
        />
        <Route
          path="/vendor/proposals/:proposalId"
          element={
            <VendorLayout>
              <VendorProposalDetailPage />
            </VendorLayout>
          }
        />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
