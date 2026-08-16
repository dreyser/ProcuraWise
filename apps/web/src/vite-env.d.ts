/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Fase 28: absolute origin of the real API when the SPA is served from a
   * different Container App than the API (empty in dev, where Vite's own
   * proxy handles same-origin `/api`/`/health` - see vite.config.ts). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
