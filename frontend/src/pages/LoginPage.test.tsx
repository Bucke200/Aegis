import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMe, login } from '../api/auth'
import { ApiError } from '../api/client'
import type { MeResponse, TokenResponse } from '../api/types'
import { AuthProvider } from '../auth/AuthContext'
import { LoginPage } from './LoginPage'

vi.mock('../api/auth', () => ({
  login: vi.fn(),
  fetchMe: vi.fn(),
  logout: vi.fn(),
  enrollMfa: vi.fn(),
  verifyMfa: vi.fn(),
}))

const meResponse: MeResponse = {
  user: {
    id: 'u1',
    email: 'analyst@example.test',
    display_name: 'Analyst',
    role: 'analyst',
    mfa_enabled: true,
    is_active: true,
    created_at: '2026-10-05T12:00:00Z',
  },
  scopes: [],
}

function renderLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/incidents" element={<div>incident feed</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.mocked(fetchMe).mockRejectedValue(new ApiError(401, 'missing token'))
  })

  it('reveals the MFA field after an invalid MFA code', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockRejectedValueOnce(new ApiError(401, 'invalid MFA code'))
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'analyst@example.test')
    await user.type(screen.getByLabelText('Password'), 'secret')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/Enter the 6-digit code/)).toBeInTheDocument()

    vi.mocked(login).mockResolvedValueOnce({
      access_token: 'access',
      token_type: 'bearer',
      role: 'analyst',
    } satisfies TokenResponse)
    vi.mocked(fetchMe).mockResolvedValueOnce(meResponse)

    await user.type(screen.getByLabelText('Authenticator code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(login).toHaveBeenLastCalledWith('analyst@example.test', 'secret', '123456')
    })
    expect(await screen.findByText('incident feed')).toBeInTheDocument()
  })

  it('shows an error for invalid credentials', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockRejectedValueOnce(new ApiError(401, 'invalid credentials'))
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'analyst@example.test')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
  })
})
