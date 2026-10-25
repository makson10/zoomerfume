import { Code, Group, Loader, Paper, Stack, Text } from '@mantine/core'
import { memo } from 'react'
import type { NoteDecision } from '../api/notes.ts'
import type { ChatMessage } from '../hooks/useChat.ts'
import { CitationChip } from './CitationChip.tsx'
import { CostBadge } from './CostBadge.tsx'
import { MarkdownText } from './MarkdownText.tsx'
import { PendingNoteCard } from './PendingNoteCard.tsx'
import { StepLog } from './StepLog.tsx'

interface MessageBubbleProps {
  message: ChatMessage
  /** Opens a cited record. Without it, citations stay plain text. */
  onOpenRecord?: (recordId: string) => void
  /** Confirms or rejects a note the reply proposed. Without it, no note cards show. */
  onDecideNote?: (id: string, decision: NoteDecision) => Promise<void>
}

/**
 * One chat message. It is memoized, so a streamed token re-renders and re-parses only
 * the reply it belongs to.
 */
export const MessageBubble = memo(function MessageBubble({
  message,
  onOpenRecord,
  onDecideNote,
}: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <Paper
        px="md"
        py="xs"
        maw="85%"
        bg="var(--mantine-primary-color-light)"
        style={{ alignSelf: 'flex-end' }}
      >
        <Text style={{ whiteSpace: 'pre-wrap' }}>{message.content}</Text>
      </Paper>
    )
  }

  const { citations } = message
  const renderCitation = onOpenRecord
    ? (recordId: string) => (
        <CitationChip
          recordId={recordId}
          invalid={citations?.invalid.includes(recordId)}
          onOpen={onOpenRecord}
        />
      )
    : undefined

  return (
    <Stack gap={6} maw="85%" style={{ alignSelf: 'flex-start' }}>
      {message.status === 'running' && !message.content ? (
        <Loader type="dots" size="sm" />
      ) : (
        <Paper px="md" py="xs" withBorder>
          <MarkdownText renderCitation={renderCitation}>
            {message.content}
          </MarkdownText>
        </Paper>
      )}
      {message.activeTool && (
        <Text size="xs" c="dimmed">
          Using <Code>{message.activeTool}</Code>…
        </Text>
      )}
      {onDecideNote &&
        message.notes?.map((note) => (
          <PendingNoteCard key={note.id} note={note} onDecide={onDecideNote} />
        ))}
      {citations && onOpenRecord && citations.valid.length > 0 && (
        <Group gap={4}>
          <Text size="xs" c="dimmed">
            Sources:
          </Text>
          {citations.valid.map((recordId) => (
            <CitationChip
              key={recordId}
              recordId={recordId}
              onOpen={onOpenRecord}
            />
          ))}
        </Group>
      )}
      {citations && (
        <StepLog
          steps={message.steps ?? []}
          citations={citations}
          stopped={message.status === 'cancelled'}
        />
      )}
      {message.usage && message.usage.calls > 0 && (
        <CostBadge usage={message.usage} />
      )}
    </Stack>
  )
})
