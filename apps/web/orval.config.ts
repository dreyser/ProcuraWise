import { defineConfig } from 'orval'

export default defineConfig({
  procurawise: {
    input: './openapi.json',
    output: {
      target: './src/api/client.ts',
      client: 'fetch',
    },
  },
})
