import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/lib/http'

/** 4xx responses (403/404/422/...) are never transient - retrying wastes a
 * round trip and delays the error/empty state the UI should show instead. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 1
}

/**
 * A fresh instance is created per active actor (see ActorProvider) so that
 * switching actors always starts from an empty cache - no data from a
 * previous tenant/role can leak into the next selection (brief §13/§27).
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
}
