import { Button, Group, Paper, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import type { NoteDecision, ProposedNote } from '../api/notes.ts'

interface PendingNoteCardProps {
  note: ProposedNote
  /** Confirms or rejects the note. Rejects when the decision isn't stored. */
  onDecide: (id: string, decision: NoteDecision) => Promise<void>
}

/**
 * A note Zoomer proposed. While it is pending, the customer saves it or drops it here;
 * Zoomer has no way to do either. Afterwards one line says what happened to it.
 */
export function PendingNoteCard({ note, onDecide }: PendingNoteCardProps) {
  const [deciding, setDeciding] = useState<NoteDecision | null>(null)
  const [failed, setFailed] = useState(false)

  if (note.status !== 'pending') {
    return (
      <Text size="xs" c="dimmed">
        {note.status === 'confirmed' ? 'Saved to your notes' : 'Not saved'}: “
        {note.text}”
      </Text>
    )
  }

  async function decide(decision: NoteDecision) {
    setDeciding(decision)
    setFailed(false)
    try {
      await onDecide(note.id, decision)
    } catch {
      setFailed(true)
    } finally {
      setDeciding(null)
    }
  }

  return (
    <Paper withBorder p="xs">
      <Stack gap={6}>
        <Text size="xs" c="dimmed">
          Zoomer wants to save a note. Save it?
        </Text>
        <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
          {note.text}
        </Text>
        <Group gap="xs">
          <Button
            size="compact-sm"
            loading={deciding === 'confirm'}
            disabled={deciding !== null}
            onClick={() => void decide('confirm')}
          >
            Save
          </Button>
          <Button
            size="compact-sm"
            variant="default"
            loading={deciding === 'reject'}
            disabled={deciding !== null}
            onClick={() => void decide('reject')}
          >
            Don't save
          </Button>
        </Group>
        {failed && (
          <Text size="xs" c="red">
            Couldn't store your choice. Please try again.
          </Text>
        )}
      </Stack>
    </Paper>
  )
}
