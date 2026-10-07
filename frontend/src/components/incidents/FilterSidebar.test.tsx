import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { EMPTY_FILTERS } from '../../api/incidents'
import { FilterSidebar } from './FilterSidebar'

describe('FilterSidebar', () => {
  it('emits a severity filter change', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <FilterSidebar
        filters={EMPTY_FILTERS}
        onChange={onChange}
        vips={[]}
        assignees={[]}
        showAssignees={false}
        open={false}
        onClose={() => undefined}
      />,
    )

    await user.click(screen.getByRole('checkbox', { name: 'critical' }))
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTERS, severity: ['critical'] })
  })

  it('lists VIPs and the include-merged toggle', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <FilterSidebar
        filters={EMPTY_FILTERS}
        onChange={onChange}
        vips={[
          {
            id: 'v1',
            name: 'Asha Verma',
            sensitivity: 'high',
            monitoring_active: true,
            config_version: 1,
            created_at: '2026-10-05T12:00:00Z',
          },
        ]}
        assignees={[
          { id: 'u1', email: 'lead@example.test', display_name: 'Lead', role: 'lead' },
        ]}
        showAssignees
        open={false}
        onClose={() => undefined}
      />,
    )

    await user.click(screen.getByRole('checkbox', { name: 'Asha Verma' }))
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTERS, vipId: ['v1'] })

    await user.click(screen.getByRole('checkbox', { name: 'Lead' }))
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTERS, assigneeId: ['u1'] })

    await user.click(screen.getByRole('checkbox', { name: 'Include merged' }))
    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_FILTERS, includeMerged: true })
  })
})
