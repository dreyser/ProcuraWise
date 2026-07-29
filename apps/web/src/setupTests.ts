import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Vitest isn't run with `test.globals: true`, so Testing Library's
// auto-cleanup (which relies on detecting a global `afterEach`) never
// registers on its own - without this, DOM from one test file's renders
// leaks into the next, causing spurious "multiple elements found" queries.
afterEach(() => {
  cleanup()
})
