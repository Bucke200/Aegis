import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Detection } from '../../api/types'
import { DetectionPanel, HighlightedText } from './DetectionPanel'

describe('HighlightedText', () => {
  it('marks offset spans and merges overlaps', () => {
    render(
      <HighlightedText
        text="I will shoot him tomorrow"
        spans={[
          { start: 7, end: 12, category: 'threat_verbs' },
          { start: 10, end: 12, category: 'weapons' },
          { start: 17, end: 25, category: 'specificity' },
        ]}
      />,
    )
    const marks = screen.getAllByTestId('span-highlight')
    expect(marks.map((mark) => mark.textContent)).toEqual(['shoot', 'tomorrow'])
  })

  it('ignores out-of-range offsets', () => {
    render(<HighlightedText text="short" spans={[{ start: 100, end: 120 }]} />)
    expect(screen.queryByTestId('span-highlight')).not.toBeInTheDocument()
    expect(screen.getByText('short')).toBeInTheDocument()
  })
})

describe('DetectionPanel', () => {
  const detection: Detection = {
    id: 'd1',
    detector: 'text_intent_llm',
    model_version: 'gpt:1',
    input_variant: 'text',
    score: 0.91,
    label: 'violent_threat',
    spans: [
      { start: 7, end: 12, category: 'threat_verbs' },
      { text: 'anonymous fragment' },
    ],
    details: { rationale: 'Explicit threat.', specificity: { time: 'tomorrow' } },
    created_at: '2026-10-05T12:00:00Z',
  }

  it('renders score, rationale, specificity, fragments, and highlights', () => {
    render(<DetectionPanel detections={[detection]} itemText="I will shoot him tomorrow" />)
    expect(screen.getByText('text_intent_llm')).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('Explicit threat.')).toBeInTheDocument()
    expect(screen.getByText('anonymous fragment')).toBeInTheDocument()
    expect(screen.getByTestId('span-highlight')).toHaveTextContent('shoot')
  })
})
