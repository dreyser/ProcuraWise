import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createAppQueryClient } from '@/lib/queryClient'
import { AuthProvider } from '@/auth/AuthContext'
import { ActorProvider } from '@/actor/ActorContext'
import { AppRouter } from '@/app/router'

function App() {
  // Single app-wide QueryClient, created once - both AuthProvider (buyer,
  // real JWT) and ActorProvider (vendor_contact, interim dev header) share
  // it via useQueryClient() and each call .clear() on their own
  // login/logout/switch, rather than each provider owning its own client.
  // Two independent QueryClientProviders would make the innermost one win
  // for every descendant, defeating either side's "no cache leaks between
  // identities" guarantee unpredictably.
  const [queryClient] = useState(() => createAppQueryClient())

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ActorProvider>
          <AppRouter />
        </ActorProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
