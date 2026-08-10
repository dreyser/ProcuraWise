import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

/**
 * Fase 26 (Hardening, plan Bloque 5): asserts the current page has no
 * automatically-detectable WCAG 2.1 AA violations (axe-core - the same
 * ruleset browser extensions like axe DevTools use). Scoped to
 * wcag2a/wcag2aa/wcag21a/wcag21aa - the AA bar this phase targets, not
 * axe's broader "best-practice" rules that sit outside the WCAG standard
 * itself. Called at least once per existing E2E spec (100% automated
 * coverage); called at multiple points within vertical-slice.spec.ts (the
 * two flagship journeys the founder named as needing deeper coverage:
 * buyer owner end-to-end, vendor answering a proposal).
 */
export async function checkA11y(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()

  const summary = results.violations
    .map(
      (v) =>
        `[${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s)) - ${v.nodes
          .map((n) => n.target.join(' '))
          .join(', ')}`,
    )
    .join('\n')

  expect(results.violations, summary).toEqual([])
}

/**
 * Fase 26 (Hardening, plan Bloque 5): the deeper, Playwright-driven check
 * standing in for a manual accessibility pass on the two flagship journeys
 * (no human tester/screen reader is available in this environment) -
 * repeatedly presses Tab and asserts that whatever receives focus, if
 * anything, is visible. This catches the specific, common keyboard-trap
 * failure mode axe-core's static analysis of a page's DOM snapshot cannot:
 * focus silently landing on (or moving to) an element a sighted keyboard
 * user can't see.
 */
export async function assertKeyboardFocusStaysVisible(page: Page, tabPresses = 15): Promise<void> {
  for (let i = 0; i < tabPresses; i += 1) {
    await page.keyboard.press('Tab')
    const focused = page.locator(':focus')
    if ((await focused.count()) === 0) {
      continue
    }
    await expect(focused).toBeVisible()
  }
}
