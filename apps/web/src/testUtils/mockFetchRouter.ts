interface RouteContext {
  url: URL
  headers: Headers
  body: unknown
}

interface RouteResult {
  status: number
  body?: unknown
}

type Handler = (ctx: RouteContext) => RouteResult | Promise<RouteResult>

interface Route {
  method: string
  pattern: RegExp
  handler: Handler
}

/**
 * Minimal method+path router standing in for the real API in integration
 * tests (brief §28.C) - avoids pulling in MSW for what a handful of `fetch`
 * stubs already cover, consistent with the manual-mock pattern already used
 * in App.test.tsx.
 */
export function createFetchRouter() {
  const routes: Route[] = []

  function on(method: string, pattern: RegExp, handler: Handler) {
    routes.push({ method: method.toUpperCase(), pattern, handler })
  }

  const fetchImpl: typeof fetch = async (input, init) => {
    const rawUrl =
      typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const url = new URL(rawUrl, 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const headers = new Headers(init?.headers)
    const body = init?.body ? JSON.parse(init.body as string) : undefined

    const match = routes.find(
      (route) => route.method === method && route.pattern.test(url.pathname),
    )
    if (!match) {
      throw new Error(`No mock route registered for ${method} ${url.pathname}`)
    }

    const result = await match.handler({ url, headers, body })
    // A plain object matching the subset of the Response interface apiFetch
    // actually reads - constructing a real `Response` in jsdom has caused
    // requests to hang indefinitely rather than resolve or reject.
    return {
      ok: result.status >= 200 && result.status < 300,
      status: result.status,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => result.body,
      text: async () => JSON.stringify(result.body ?? ''),
    } as Response
  }

  return { on, fetchImpl }
}
