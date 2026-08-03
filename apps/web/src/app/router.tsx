import { type ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { useVendorAuth } from '@/vendor-auth/VendorAuthContext'
import { RequireAuth, RequireRole, RequireVendorAuth } from '@/app/guards'
import { AppShell } from '@/app/AppShell'
import { roleHomePath } from '@/app/roleHomePath'
import { SelectActorPage } from '@/actor/SelectActorPage'
import { LoginPage } from '@/auth/LoginPage'
import { AuthCallbackPage } from '@/auth/AuthCallbackPage'
import { SelectWorkspacePage } from '@/auth/SelectWorkspacePage'
import { VendorLoginPage } from '@/vendor-auth/VendorLoginPage'
import { AcceptInvitationPage } from '@/vendor-auth/AcceptInvitationPage'
import { RequireAgreementsAccepted } from '@/features/agreements/RequireAgreementsAccepted'
import { UnauthorizedPage } from '@/app/UnauthorizedPage'
import { NotFoundPage } from '@/app/NotFoundPage'
import { EvaluationListPage } from '@/features/evaluations/pages/EvaluationListPage'
import { EvaluationWizard } from '@/features/evaluations/wizard/EvaluationWizard'
import { EvaluationDetailPage } from '@/features/evaluations/pages/EvaluationDetailPage'
import { RequirementsPage } from '@/features/evaluations/pages/RequirementsPage'
import { VendorsPage } from '@/features/evaluations/pages/VendorsPage'
import { ProposalsPage } from '@/features/proposals/pages/ProposalsPage'
import { ScoringPage } from '@/features/scoring/pages/ScoringPage'
import { ResultsPage } from '@/features/scoring/pages/ResultsPage'
import { VendorProposalListPage } from '@/features/vendor-portal/pages/VendorProposalListPage'
import { VendorProposalDetailPage } from '@/features/vendor-portal/pages/VendorProposalDetailPage'
import { AssignmentsPage } from '@/features/evaluations/pages/AssignmentsPage'
import { EvaluationApprovalPage } from '@/features/evaluations/pages/EvaluationApprovalPage'
import { KnowledgeTemplatesPage } from '@/features/evaluations/pages/KnowledgeTemplatesPage'
import { KnowledgeTemplateDetailPage } from '@/features/evaluations/pages/KnowledgeTemplateDetailPage'
import { QnaPage } from '@/features/evaluations/pages/QnaPage'

// Fase 9 (RBAC completo, spec §4): tenant_admin/platform_admin are real,
// backend-enforced roles that can authenticate, but have no dedicated UI
// area yet (that's the admin console, Fase 25) - reaching this app with
// either lands on /unauthorized, same as any other unrecognized role.
const BUYER_ROLES = [
  'evaluation_owner',
  'evaluator_functional',
  'evaluator_technical',
  'evaluator_economic',
  'internal_collaborator',
  'approver',
]
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
  const { actor, logout } = useVendorAuth()
  const navigate = useNavigate()

  return (
    <RequireVendorAuth>
      <RequireRole roles={VENDOR_ROLES} actor={actor}>
        {actor ? (
          <AppShell
            actor={actor}
            exitLabel="Cerrar sesión"
            onExit={() => {
              logout()
              navigate('/vendor/login', { replace: true })
            }}
          >
            <RequireAgreementsAccepted>{children}</RequireAgreementsAccepted>
          </AppShell>
        ) : (
          <></>
        )}
      </RequireRole>
    </RequireVendorAuth>
  )
}

function RootRedirect() {
  const { status: authStatus, actor: buyerActor } = useAuth()
  const { status: vendorAuthStatus, actor: vendorActor } = useVendorAuth()

  if (authStatus === 'ready' && buyerActor) {
    return <Navigate to={roleHomePath(buyerActor.role)} replace />
  }
  if (authStatus === 'awaiting_workspace') {
    return <Navigate to="/auth/select-workspace" replace />
  }
  if (vendorAuthStatus === 'ready' && vendorActor) {
    return <Navigate to={roleHomePath(vendorActor.role)} replace />
  }
  // Neither a buyer nor a vendor session is active - real auth for either
  // (Fase 15) is never persisted across a refresh, so there is no reliable
  // signal here for which login screen to prefer. Buyer is the more common
  // entry point; a vendor hitting a specific deep link still lands on
  // /vendor/login via RequireVendorAuth's own redirect, which does know.
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
        <Route path="/vendor/login" element={<VendorLoginPage />} />
        <Route path="/vendor/accept-invitation" element={<AcceptInvitationPage />} />
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
          path="/knowledge-templates"
          element={
            <BuyerLayout>
              <KnowledgeTemplatesPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/knowledge-templates/:templateId"
          element={
            <BuyerLayout>
              <KnowledgeTemplateDetailPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/new"
          element={
            <BuyerLayout>
              <EvaluationWizard />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/wizard"
          element={
            <BuyerLayout>
              <EvaluationWizard />
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
          path="/evaluations/:evaluationId/assignments"
          element={
            <BuyerLayout>
              <AssignmentsPage />
            </BuyerLayout>
          }
        />
        <Route
          path="/evaluations/:evaluationId/approval"
          element={
            <BuyerLayout>
              <EvaluationApprovalPage />
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
          path="/evaluations/:evaluationId/qna"
          element={
            <BuyerLayout>
              <QnaPage />
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
