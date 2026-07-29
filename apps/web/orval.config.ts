import { defineConfig } from 'orval'

export default defineConfig({
  procurawise: {
    input: './openapi.json',
    output: {
      target: './src/api/client.ts',
      client: 'react-query',
      httpClient: 'fetch',
      override: {
        mutator: {
          path: './src/lib/http.ts',
          name: 'apiFetch',
        },
        // orval@7.21's react-query+fetch generator, when a custom mutator is
        // supplied, still types the base function's second parameter as a
        // literal `RequestInit` but (with query.signal left at its default)
        // calls it with a bare `AbortSignal` for cancellation - a real type
        // mismatch (TS2559) between the generated call site and its own
        // declared signature, not something fixable from the mutator side.
        // Disabling query-driven abort signals sidesteps it; no query in
        // this slice relies on request cancellation on unmount.
        query: {
          signal: false,
        },
      },
      // Orval's fetch-client template emits trailing whitespace on several
      // blank/brace lines (a template quirk, not something the input spec
      // controls) - orval's own official mechanism for post-processing
      // generated output is this flag, which shells out to the local
      // `prettier` binary on every generated file right after writing it.
      prettier: true,
    },
  },
})
