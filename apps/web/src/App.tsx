import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createAppQueryClient } from '@/lib/queryClient'
import { AuthProvider } from '@/auth/AuthContext'
import { ActorProvider } from '@/actor/ActorContext'
import { VendorAuthProvider } from '@/vendor-auth/VendorAuthContext'
import { AppRouter } from '@/app/router'

function App() {
  // Single app-wide QueryClient, created once - AuthProvider (buyer, real
  // JWT), VendorAuthProvider (vendor_contact, real JWT - Fase 15), and
  // ActorProvider (interim dev header, kept only for /dev/select-actor
  // devtools exploration - no longer wired into any production route) all
  // share it via useQueryClient() and each call .clear() on their own
  // login/logout/switch, rather than each provider owning its own client.
  // Two independent QueryClientProviders would make the innermost one win
  // for every descendant, defeating each side's "no cache leaks between
  // identities" guarantee unpredictably.
  const [queryClient] = useState(() => createAppQueryClient())

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <VendorAuthProvider>
          <ActorProvider>
            <AppRouter />
          </ActorProvider>
        </VendorAuthProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
