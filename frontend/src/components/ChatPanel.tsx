import { Container, ScrollArea } from '@mantine/core'
import type { ChatMessage } from '../hooks/useChat.ts'
import { Composer } from './Composer.tsx'
import { MessageList } from './MessageList.tsx'

interface ChatPanelProps {
  messages: ChatMessage[]
  loading: boolean
  /** A reply is streaming in: the composer offers Stop instead of Send. */
  streaming?: boolean
  error: string | null
  emptyText?: string
  placeholder?: string
  onSend: (text: string) => void | Promise<boolean>
  onStop?: () => void
  /** Opens a cited record. Without it, citations stay plain text. */
  onOpenRecord?: (recordId: string) => void
}

/** The message list with the composer under it. Sending is blocked while loading or streaming. */
export function ChatPanel({
  messages,
  loading,
  streaming = false,
  error,
  emptyText,
  placeholder,
  onSend,
  onStop,
  onOpenRecord,
}: ChatPanelProps) {
  return (
    <Container
      size="sm"
      h="100%"
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      <ScrollArea flex={1} mih={0}>
        <MessageList
          messages={messages}
          loading={loading}
          error={error}
          emptyText={emptyText}
          onOpenRecord={onOpenRecord}
        />
      </ScrollArea>
      <Composer
        onSend={onSend}
        onStop={streaming ? onStop : undefined}
        disabled={loading || streaming}
        placeholder={placeholder}
      />
    </Container>
  )
}
