import { Button, Code, Collapse, Stack, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import type { Citations, Step } from '../api/chat.ts'

interface StepLogProps {
  steps: Step[]
  citations: Citations
  /** The customer stopped this answer. */
  stopped?: boolean
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, value]) => value !== null)
    .map(([name, value]) => `${name}: ${JSON.stringify(value)}`)
    .join(', ')
}

/** Red for a failed or refused call. A note waiting for the customer isn't a failure. */
function resultColor(step: Step): string | undefined {
  if (step.success) return undefined
  return step.code === 'CONFIRMATION_REQUIRED' ? 'orange' : 'red'
}

function resultText(step: Step): string {
  if (!step.success) return step.code ?? 'failed'
  if (step.record_ids.length > 0) return step.record_ids.join(', ')
  return step.tool === 'save_note' ? 'saved' : 'nothing found'
}

function StepRow({ step }: { step: Step }) {
  return (
    <Text size="xs">
      {step.step}. <Code>{step.tool}</Code>({formatArgs(step.args)}) →{' '}
      <Text span inherit c={resultColor(step)}>
        {resultText(step)}
      </Text>{' '}
      <Text span inherit c="dimmed">
        · {step.duration_ms} ms
      </Text>
    </Text>
  )
}

function Notes({
  citations,
  stopped,
}: {
  citations: Citations
  stopped: boolean
}) {
  return (
    <>
      {stopped && (
        <Text size="xs" c="dimmed">
          Stopped
        </Text>
      )}
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

/**
 * The tools Zoomer used for one answer, collapsed by default, plus a note when the
 * answer was stopped and any citation problems.
 */
export function StepLog({ steps, citations, stopped = false }: StepLogProps) {
  const [opened, { toggle }] = useDisclosure(false)

  if (steps.length === 0) {
    return (
      <Stack gap={2}>
        <Text size="xs" c="dimmed">
          No tools used
        </Text>
        <Notes citations={citations} stopped={stopped} />
      </Stack>
    )
  }

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
        {steps.length === 1 ? '1 tool call' : `${steps.length} tool calls`}
      </Button>
      <Collapse expanded={opened}>
        <Stack gap={4} pl="md">
          {steps.map((step) => (
            <StepRow key={step.step} step={step} />
          ))}
        </Stack>
      </Collapse>
      <Notes citations={citations} stopped={stopped} />
    </Stack>
  )
}
