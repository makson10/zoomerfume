import { Button, Code, Collapse, Stack, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import type { Citations, Step } from '../api/chat.ts'

interface StepLogProps {
  steps: Step[]
  citations: Citations
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, value]) => value !== null)
    .map(([name, value]) => `${name}: ${JSON.stringify(value)}`)
    .join(', ')
}

function StepRow({ step }: { step: Step }) {
  let result: string
  if (!step.success) result = step.code ?? 'failed'
  else if (step.record_ids.length > 0) result = step.record_ids.join(', ')
  else result = 'nothing found'

  return (
    <Text size="xs">
      {step.step}. <Code>{step.tool}</Code>({formatArgs(step.args)}) →{' '}
      <Text span inherit c={step.success ? undefined : 'red'}>
        {result}
      </Text>{' '}
      <Text span inherit c="dimmed">
        · {step.duration_ms} ms
      </Text>
    </Text>
  )
}

function CitationWarnings({ citations }: { citations: Citations }) {
  return (
    <>
      {citations.invalid.length > 0 && (
        <Text size="xs" c="red">
          Cites records no tool returned: {citations.invalid.join(', ')}
        </Text>
      )}
      {citations.missing && (
        <Text size="xs" c="orange">
          Doesn't cite any record found for this answer
        </Text>
      )}
    </>
  )
}

/** The tools Zoomer used for one answer, collapsed by default, and any citation problems. */
export function StepLog({ steps, citations }: StepLogProps) {
  const [opened, { toggle }] = useDisclosure(false)

  if (steps.length === 0) {
    return (
      <Stack gap={2}>
        <Text size="xs" c="dimmed">
          No tools used
        </Text>
        <CitationWarnings citations={citations} />
      </Stack>
    )
  }

  const seconds =
    steps.reduce((total, step) => total + step.duration_ms, 0) / 1000
  const Chevron = opened ? IconChevronDown : IconChevronRight

  return (
    <Stack gap={2} align="flex-start">
      <Button
        variant="subtle"
        color="gray"
        size="compact-xs"
        leftSection={<Chevron size={14} />}
        onClick={toggle}
      >
        {steps.length === 1 ? '1 tool call' : `${steps.length} tool calls`} ·{' '}
        {seconds.toFixed(1)} s
      </Button>
      <Collapse expanded={opened}>
        <Stack gap={4} pl="md">
          {steps.map((step) => (
            <StepRow key={step.step} step={step} />
          ))}
        </Stack>
      </Collapse>
      <CitationWarnings citations={citations} />
    </Stack>
  )
}
