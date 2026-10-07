import type { Detection, DetectionSpan } from '../../api/types'

interface Interval {
  start: number
  end: number
  category?: string
}

function offsetIntervals(spans: DetectionSpan[], textLength: number): Interval[] {
  const intervals: Interval[] = []
  for (const span of spans) {
    if (typeof span.start !== 'number' || typeof span.end !== 'number') {
      continue
    }
    const start = Math.max(0, Math.min(span.start, textLength))
    const end = Math.max(start, Math.min(span.end, textLength))
    if (end > start) {
      intervals.push({ start, end, category: span.category })
    }
  }
  return intervals.sort((left, right) => left.start - right.start)
}

function mergeIntervals(intervals: Interval[]): Interval[] {
  const merged: Interval[] = []
  for (const interval of intervals) {
    const previous = merged.at(-1)
    if (previous && interval.start <= previous.end) {
      previous.end = Math.max(previous.end, interval.end)
      if (interval.category && previous.category !== interval.category) {
        previous.category = `${previous.category ?? 'span'}, ${interval.category}`
      }
    } else {
      merged.push({ ...interval })
    }
  }
  return merged
}

export function HighlightedText({ text, spans }: { text: string; spans: DetectionSpan[] }) {
  const merged = mergeIntervals(offsetIntervals(spans, text.length))
  if (merged.length === 0) {
    return <p className="whitespace-pre-wrap text-sm text-slate-800">{text}</p>
  }

  const segments: Array<{ key: string; content: string; category?: string; isMark: boolean }> = []
  let cursor = 0
  merged.forEach((interval, index) => {
    if (interval.start > cursor) {
      segments.push({ key: `plain-${index}`, content: text.slice(cursor, interval.start), isMark: false })
    }
    segments.push({
      key: `mark-${index}`,
      content: text.slice(interval.start, interval.end),
      category: interval.category,
      isMark: true,
    })
    cursor = interval.end
  })
  if (cursor < text.length) {
    segments.push({ key: 'plain-tail', content: text.slice(cursor), isMark: false })
  }

  return (
    <p className="whitespace-pre-wrap text-sm text-slate-800">
      {segments.map((segment) =>
        segment.isMark ? (
          <mark
            key={segment.key}
            title={segment.category}
            className="rounded bg-amber-200 px-0.5 text-slate-900"
            data-testid="span-highlight"
          >
            {segment.content}
          </mark>
        ) : (
          <span key={segment.key}>{segment.content}</span>
        ),
      )}
    </p>
  )
}

export function DetectionPanel({ detections, itemText }: { detections: Detection[]; itemText: string | null }) {
  if (detections.length === 0) {
    return <p className="text-sm text-slate-500">No detections recorded.</p>
  }
  return (
    <ul className="space-y-3">
      {detections.map((detection) => {
        const fragments = detection.spans.filter(
          (span) => typeof span.start !== 'number' && typeof span.text === 'string' && span.text,
        )
        const rationale = typeof detection.details.rationale === 'string' ? detection.details.rationale : null
        const specificity = detection.details.specificity
        return (
          <li key={detection.id} data-testid="detection" className="rounded border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{detection.detector}</span>
              <span className="text-slate-500">v{detection.model_version}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                {detection.input_variant}
              </span>
              {detection.label ? <span className="text-xs text-slate-600">label: {detection.label}</span> : null}
              <span className="ml-auto font-mono text-sm">{(detection.score * 100).toFixed(0)}%</span>
            </div>
            {detection.input_variant === 'text' && itemText && detection.spans.length > 0 ? (
              <div className="mt-2 rounded bg-slate-50 p-2">
                <HighlightedText text={itemText} spans={detection.spans} />
              </div>
            ) : null}
            {fragments.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {fragments.map((span, index) => (
                  <span key={index} className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                    {String(span.text)}
                  </span>
                ))}
              </div>
            ) : null}
            {rationale ? <p className="mt-2 text-xs text-slate-500">{rationale}</p> : null}
            {specificity && typeof specificity === 'object' ? (
              <p className="mt-1 text-xs text-slate-500">
                specificity:{' '}
                {Object.entries(specificity as Record<string, unknown>)
                  .filter(([, value]) => Boolean(value))
                  .map(([key, value]) => `${key}=${String(value)}`)
                  .join(', ') || 'none'}
              </p>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
