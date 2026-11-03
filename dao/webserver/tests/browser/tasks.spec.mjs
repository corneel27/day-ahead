import { test, expect } from '@playwright/test'

const pageErrors = new WeakMap()

test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/v2/tasks')
  await expect(page.locator('#status-target h2')).toContainText('idle')
  await page.evaluate(() => { window.documentMarker = 'preserved' })
})

async function openTaskMenu(page) {
  await page.getByRole('button', { name: 'Pick action' }).click()
}

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([])
})

test('boosted task submission polls and swaps status without navigation', async ({ page }) => {
  const initialURL = page.url()
  const initialHistory = await page.evaluate(() => history.length)
  let statusRequests = 0
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/v2/task-state') statusRequests += 1
  })
  const submitted = page.waitForRequest(request =>
    new URL(request.url()).pathname === '/v2/task-exec' && request.method() === 'POST')
  await openTaskMenu(page)
  await page.getByRole('button', { name: 'Run synthetic task', exact: true }).click()
  const request = await submitted
  expect(request.headers()['hx-request']).toBe('true')
  expect(request.headers()['hx-boosted']).toBe('true')
  expect(new URLSearchParams(request.postData()).get('task')).toBe('complete')
  await expect(page.locator('#status-target h2')).toContainText('running')
  await expect(page.locator('#run-cancel')).not.toHaveClass(/disabled/)
  await expect(page.locator('#status-target h2')).toContainText('completed', { timeout: 10_000 })
  await expect(page.locator('#run-cancel')).toHaveClass(/disabled/)
  expect(statusRequests).toBeGreaterThanOrEqual(3)
  expect(page.url()).toBe(initialURL)
  expect(await page.evaluate(() => history.length)).toBe(initialHistory)
  expect(await page.evaluate(() => window.documentMarker)).toBe('preserved')
  await expect(page.locator('#status-target h2')).toHaveCount(1)
  await expect(page.locator('footer')).toHaveCount(1)
  await expect(page.locator('#htmx-error')).toBeHidden()
})

test('cancellation updates the existing task status without an error banner', async ({ page }) => {
  const initialURL = page.url()
  await openTaskMenu(page)
  await page.getByRole('button', { name: 'Run cancellable task', exact: true }).click()
  await expect(page.locator('#status-target h2')).toContainText('running')
  await page.locator('#run-cancel').click()
  await expect(page.locator('#status-target h2')).toContainText('cancelled')
  await expect(page.locator('#status-target h2')).toHaveCount(1)
  await expect(page.locator('footer')).toHaveCount(1)
  await expect(page.locator('#run-cancel')).toHaveClass(/disabled/)
  await expect(page.locator('#htmx-error')).toBeHidden()
  expect(page.url()).toBe(initialURL)
  expect(await page.evaluate(() => window.documentMarker)).toBe('preserved')
})

test('HTTP errors show the application banner and preserve the current status', async ({ page }) => {
  await openTaskMenu(page)
  const button = page.getByRole('button', { name: 'Run synthetic task', exact: true })
  await button.evaluate(element => { element.value = 'unknown-task' })
  await button.click()
  await expect(page.locator('#htmx-error')).toBeVisible()
  await expect(page.locator('#htmx-error-message')).toHaveText('Invalid task')
  await expect(page.locator('#status-target h2')).toContainText('idle')
  expect(await page.evaluate(() => window.documentMarker)).toBe('preserved')
  await page.locator('#htmx-error .btn-close').click()
  await expect(page.locator('#htmx-error')).toBeHidden()
})

test('connection failures show the application connection-error banner', async ({ page }) => {
  await page.route('**/v2/task-exec', route => route.abort('failed'))
  await openTaskMenu(page)
  await page.getByRole('button', { name: 'Run synthetic task', exact: true }).click()
  await expect(page.locator('#htmx-error')).toBeVisible()
  await expect(page.locator('#htmx-error-message')).toHaveText('De server kon niet worden bereikt.')
  await expect(page.locator('#status-target h2')).toContainText('idle')
})
