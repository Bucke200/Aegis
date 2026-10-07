import { authenticator } from 'otplib'
import { expect, test } from '@playwright/test'

const apiUrl = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'

test('enrols MFA and signs in with a one-time code', async ({ page, request }) => {
  const loginResponse = await request.post(`${apiUrl}/auth/login`, {
    data: { email: 'e2e-mfa@example.test', password: 'e2e-mfa-password' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const { access_token: accessToken } = (await loginResponse.json()) as { access_token: string }

  const enrollResponse = await request.post(`${apiUrl}/auth/mfa/enroll`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  expect(enrollResponse.ok()).toBeTruthy()
  const { secret } = (await enrollResponse.json()) as { secret: string }

  const enrollCode = authenticator.generate(secret)
  const verifyResponse = await request.post(`${apiUrl}/auth/mfa/verify`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { code: enrollCode },
  })
  expect(verifyResponse.ok()).toBeTruthy()

  await page.goto('/login')
  await page.getByLabel('Email').fill('e2e-mfa@example.test')
  await page.getByLabel('Password').fill('e2e-mfa-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByText(/Enter the 6-digit code/)).toBeVisible()
  await page.getByLabel('Authenticator code').fill(authenticator.generate(secret))
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/incidents/, { timeout: 15_000 })
})
