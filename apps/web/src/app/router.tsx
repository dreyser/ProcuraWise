import { type ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useActor } from '@/actor/ActorContext'
import { useAuth } from '@/auth/AuthContext'
import { RequireActor, RequireAuth, RequireRole } from '@/app/guards'
import { AppShell } from '@/app/AppShell'
import { roleHomePath } from '@/app/roleHomePath'
import { SelectActorPage } from '@/actor/SelectActorPage'
import { LoginPage } from '@/auth/LoginPage'
import { AuthCallbackPage } from '@/auth/AuthCallbackPage'
import { SelectWorkspacePage } from '@/auth/SelectWorkspacePage'
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
  const { actor, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <RequireAuth>
      <RequireRole roles={BUYER_ROLES} actor={actor}>
        {actor ? (
          <AppShell
            actor={actor}
            exitLabel="Cerrar sesión"
            onExit={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            {children}
          </AppShell>
        ) : (
          <></>
        )}
      </RequireRole>
    </RequireAuth>
  )
}

function VendorLayout({ children }: { children: ReactElement }) {
  const { actor, clearActor } = useActor()
  const navigate = useNavigate()

  return (
    <RequireActor>
      <RequireRole roles={VENDOR_ROLES} actor={actor}>
        {actor ? (
          <AppShell
            actor={actor}
            exitLabel="Cambiar de actor"
            devModeNotice
            onExit={() => {
              clearActor()
              navigate('/dev/select-actor', { replace: true })
            }}
          >
            {children}
          </AppShell>
        ) : (
          <></>
        )}
      </RequireRole>
    </RequireActor>
  )
}

function RootRedirect() {
  const { status: authStatus, actor: buyerActor } = useAuth()
  const { status: vendorStatus, actor: vendorActor } = useActor()

  if (authStatus === 'ready' && buyerActor) {
    return <Navigate to={roleHomePath(buyerActor.role)} replace />
  }
  if (authStatus === 'awaiting_workspace') {
    return <Navigate to="/auth/select-workspace" replace />
  }
  if (vendorStatus === 'loading') return null
  if (vendorStatus === 'ready' && vendorActor) {
    return <Navigate to={roleHomePath(vendorActor.role)} replace />
  }
  return <Navigate to="/login" replace />
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/auth/select-workspace" element={<SelectWorkspacePage />} />
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
