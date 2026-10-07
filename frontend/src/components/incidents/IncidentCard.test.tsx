import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import type { Incident } from '../../api/types'
import { IncidentCard } from './IncidentCard'

const incident: Incident = {
  id: '11111111-1111-1111-1111-111111111111',
  subject_type: 'item',
  item_id: '22222222-2222-2222-2222-222222222222',
  account_id: null,
  source: 'telegram',
  language: 'en',
  risk_score: 0.87,
  severity: 'high',
  threat_types: ['violent_threat'],
  explanation: 'High risk 0.87; signals: text_lexicon',
  status: 'new',
  assignee_id: '33333333-3333-3333-3333-333333333333',
  campaign_id: null,
  outcome: null,
  below_threshold: false,
  merged_into_id: null,
  created_at: '2026-10-05T12:00:00Z',
  updated_at: '2026-10-05T12:00:00Z',
  vip_ids: ['44444444-4444-4444-4444-444444444444'],
  item: {
    id: '22222222-2222-2222-2222-222222222222',
    source: 'telegram',
    platform_item_id: 'tg-1',
    url: 'https://example.test/tg-1',
    text: 'I will shoot the candidate tomorrow',
    language: 'en',
    collected_at: '2026-10-05T11:59:00Z',
  },
  assignee: {
    id: '33333333-3333-3333-3333-333333333333',
    email: 'analyst@example.test',
    display_name: 'Asha',
    role: 'analyst',
  },
  account: null,
}

describe('IncidentCard', () => {
  it('shows every required field', () => {
    render(
      <MemoryRouter>
        <IncidentCard
          incident={incident}
          vipNames={new Map([['44444444-4444-4444-4444-444444444444', 'Asha Verma']])}
        />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('severity-badge')).toHaveTextContent('high')
    expect(screen.getByTestId('status-badge')).toHaveTextContent('New')
    expect(screen.getByText('I will shoot the candidate tomorrow')).toBeInTheDocument()
    expect(screen.getByText('VIP: Asha Verma')).toBeInTheDocument()
    expect(screen.getByText('violent threat')).toBeInTheDocument()
    expect(screen.getByText('assignee: Asha')).toBeInTheDocument()
    expect(screen.getByText('High risk 0.87; signals: text_lexicon')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', `/incidents/${incident.id}`)
  })

  it('renders the suspect profile for account incidents', () => {
    const accountIncident: Incident = {
      ...incident,
      subject_type: 'account',
      item_id: null,
      account_id: '55555555-5555-5555-5555-555555555555',
      item: null,
      account: {
        id: '55555555-5555-5555-5555-555555555555',
        source: 'telegram',
        platform_account_id: 'acct-9',
        handle: 'fake_official',
        display_name: 'Fake Official',
      },
    }
    render(
      <MemoryRouter>
        <IncidentCard incident={accountIncident} vipNames={new Map()} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Fake Official · @fake_official')).toBeInTheDocument()
    expect(screen.getByText('account incident')).toBeInTheDocument()
  })
})
