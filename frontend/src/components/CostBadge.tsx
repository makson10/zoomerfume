import { Text } from '@mantine/core'
import type { TurnUsage } from '../api/chat.ts'

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumSignificantDigits: 2,
})

/** What one answer's model calls cost, e.g. "$0.00047 · 2 calls · 62% cached". */
export function CostBadge({ usage }: { usage: TurnUsage }) {
  const calls = usage.calls === 1 ? '1 call' : `${usage.calls} calls`
  const cached = Math.round((100 * usage.cached_tokens) / usage.input_tokens)
  return (
    <Text size="xs" c="dimmed">
      {usd.format(Number(usage.cost_usd))} · {calls} · {cached}% cached
    </Text>
  )
}
