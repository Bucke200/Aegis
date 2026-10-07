import { execFile } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const fixture = path.join(repoRoot, 'frontend', 'e2e', '.artifacts', 'incident.jsonl')

function replayFixture(): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile(
      'uv',
      ['run', 'python', '-m', 'aegis.collectors.replay', '--file', fixture, '--rate', '5'],
      { cwd: repoRoot },
      (error) => {
        if (error) {
          reject(error)
        } else {
          resolve()
        }
      },
    )
  })
}

test('login, live incident, assign, note, and resolve', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('e2e-admin@example.test')
  await page.getByLabel('Password').fill('e2e-admin-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/incidents/)
  await expect(page.getByTestId('connection-status')).toContainText('Live')

  await replayFixture()

  const card = page.getByTestId('incident-card').first()
  await expect(card).toBeVisible({ timeout: 45_000 })
  await card.click()

  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+/)
  await expect(page.getByRole('heading', { name: 'Detections' })).toBeVisible()

  await page.getByLabel('Assignee').locator('option', { hasText: 'E2E Admin' }).waitFor({ timeout: 15_000 })
  await page.getByLabel('Assignee').selectOption({ label: 'E2E Admin' })
  await page.getByRole('button', { name: 'Assign' }).click()
  await expect(page.getByText('Assigned')).toBeVisible({ timeout: 15_000 })

  await page.getByLabel('Add a note').fill('E2E note: reviewed the threat content.')
  await page.getByRole('button', { name: 'Add note' }).click()
  await expect(page.getByText('E2E note: reviewed the threat content.')).toBeVisible({ timeout: 15_000 })

  await page.getByRole('button', { name: 'Under review' }).click()
  await expect(page.getByTestId('status-badge')).toHaveText('Under review', { timeout: 15_000 })

  await page.getByRole('button', { name: 'Resolved' }).click()
  await page.getByLabel('Outcome').selectOption('reported_to_platform')
  await page.getByRole('button', { name: 'Resolve', exact: true }).click()
  await expect(page.getByTestId('status-badge')).toHaveText('Resolved', { timeout: 15_000 })
  await expect(page.getByText('Reported to platform', { exact: false })).toBeVisible()
})
