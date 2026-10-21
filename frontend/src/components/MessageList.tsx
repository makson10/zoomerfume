import { Alert, Loader, Stack, Text } from '@mantine/core'
import { useEffect, useRef } from 'react'
import type { NoteDecision } from '../api/notes.ts'
import type { ChatMessage } from '../hooks/useChat.ts'
import { MessageBubble } from './MessageBubble.tsx'

interface MessageListProps {
  messages: ChatMessage[]
  loading: boolean
  error: string | null
  /** Shown while there are no messages yet. */
  emptyText?: string
  onOpenRecord?: (recordId: string) => void
  onDecideNote?: (id: string, decision: NoteDecision) => Promise<void>
}

export function MessageList({
  messages,
  loading,
  error,
  emptyText,
  onOpenRecord,
  onDecideNote,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, error])

  return (
    <Stack gap="sm" py="md">
      {messages.length === 0 && !loading && emptyText && (
        <Text c="dimmed" ta="center" pt="xl">
          {emptyText}
        </Text>
      )}
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          onOpenRecord={onOpenRecord}
          onDecideNote={onDecideNote}
        />
      ))}
      {loading && <Loader type="dots" size="sm" />}
      {error && <Alert color="red">{error}</Alert>}
      <div ref={bottomRef} />
    </Stack>
  )
}
