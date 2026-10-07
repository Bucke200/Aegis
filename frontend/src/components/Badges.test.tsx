import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SeverityBadge, StatusBadge } from './Badges'

describe('badges', () => {
  it('renders the severity name', () => {
    render(<SeverityBadge severity="critical" />)
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('critical')
  })

  it('renders a readable status label', () => {
    render(<StatusBadge status="under_review" />)
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Under review')
  })
})
