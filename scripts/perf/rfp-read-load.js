// Fase 26 (Hardening, plan Bloque 6): k6 load test verifying NFR-003 (50
// concurrent users, global platform, not per-tenant - approved-mvp-plan.md
// S4.13) against the read path a signed-in buyer hits most: listing their
// evaluations. Deliberately read-only and idempotent, unlike the actual
// RFP write flows (creating an evaluation, submitting a proposal), which
// need real per-VU state (a distinct vendor invitation, a distinct draft
// evaluation, ...) that isn't safe to fabricate 50-wide against a shared
// local dev database without polluting `make seed-dev`'s fixtures for
// every other workflow in this repo - a candidate for a follow-up, more
// elaborate scenario once a disposable per-run tenant/data-seeding story
// exists (Fase 27+).
//
// GET /api/v1/me was tried first and dropped - it turns out to still be
// wired to the pre-AUTH-PROD dev-header identity mechanism
// (identity.dev_provider.get_current_context), not the real JWT one every
// other buyer route uses, so it 401s on a real Bearer token regardless of
// load - a real gap in that one endpoint, but outside this phase's scope
// to fix (rate limiting/CSRF/headers/WCAG/performance/backup), so this
// script just avoids it rather than silently mis-measuring against it.
//
// Authenticates ONCE in setup(), not per iteration/VU - hammering
// /auth/login itself would immediately trip the brand-new rate limiter
// added earlier in this same phase (rate_limit_login_max_attempts=5/60s per
// IP, and every k6 VU shares this machine's one IP), and a login endpoint's
// own throughput was never the NFR-003 target anyway (it has its own
// intentionally low limit as a security control, not a performance one).
//
// Usage (see docs/operations/deployment.md "Performance (k6, Fase 26)"):
//   make dev-up && make seed-dev
//   (cd service && uv run uvicorn procurawise.api.main:app --port 8000) &
//   k6 run scripts/perf/rfp-read-load.js
//
// Override the target/credentials via env vars if needed:
//   BASE_URL=http://localhost:8000 BUYER_EMAIL=owner.a@dev.procurawise.local \
//     BUYER_PASSWORD=dev-password-2026 k6 run scripts/perf/rfp-read-load.js

import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend } from 'k6/metrics'

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000'
const BUYER_EMAIL = __ENV.BUYER_EMAIL || 'owner.a@dev.procurawise.local'
const BUYER_PASSWORD = __ENV.BUYER_PASSWORD || 'dev-password-2026'

const listEvaluationsDuration = new Trend('list_evaluations_duration', true)

// NFR-003: 50 concurrent users, global. Ramps up to 50 VUs, holds for the
// bulk of the run, then ramps down - not an instantaneous spike, which
// would test something else (burst tolerance, not sustained concurrency).
export const options = {
  stages: [
    { duration: '20s', target: 50 },
    { duration: '40s', target: 50 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    // Plan Decision recomendada #4: p95 < 500ms on synchronous read
    // endpoints (AI/report endpoints are explicitly out of scope - they're
    // already async-via-job, with no synchronous SLA to measure here).
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
}

export function setup() {
  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: BUYER_EMAIL, password: BUYER_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } },
  )
  check(loginRes, { 'login succeeded': (r) => r.status === 200 })
  const preSessionToken = loginRes.json('pre_session_token')

  const membershipsRes = http.get(`${BASE_URL}/api/v1/auth/memberships`, {
    headers: { Authorization: `Bearer ${preSessionToken}` },
  })
  check(membershipsRes, { 'memberships fetched': (r) => r.status === 200 })
  const membershipId = membershipsRes.json('memberships.0.membership_id')

  const switchRes = http.post(
    `${BASE_URL}/api/v1/auth/switch-tenant`,
    JSON.stringify({ membership_id: membershipId }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${preSessionToken}`,
      },
    },
  )
  check(switchRes, { 'switch-tenant succeeded': (r) => r.status === 200 })
  const accessToken = switchRes.json('access_token')

  return { accessToken }
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.accessToken}` }

  const listRes = http.get(`${BASE_URL}/api/v1/evaluations`, { headers })
  listEvaluationsDuration.add(listRes.timings.duration)
  check(listRes, { 'list evaluations: 200': (r) => r.status === 200 })

  sleep(1)
}
