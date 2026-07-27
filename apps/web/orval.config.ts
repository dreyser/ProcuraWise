import { defineConfig } from 'orval'

export default defineConfig({
  procurawise: {
    input: './openapi.json',
    output: {
      target: './src/api/client.ts',
      client: 'fetch',
      // Orval's fetch-client template emits trailing whitespace on several
      // blank/brace lines (a template quirk, not something the input spec
      // controls) - orval's own official mechanism for post-processing
      // generated output is this flag, which shells out to the local
      // `prettier` binary on every generated file right after writing it.
      prettier: true,
    },
  },
})
