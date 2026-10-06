import { Container, ScrollArea } from '@mantine/core'
import { useState } from 'react'
import type { ChatMessage } from '../hooks/useChat.ts'
import { Composer } from './Composer.tsx'
import { MessageList } from './MessageList.tsx'

interface ChatPanelProps {
  messages: ChatMessage[]
  loading: boolean
  error: string | null
  emptyText?: string
  placeholder?: string
  onSend: (text: string) => void
}

/** The message list with the composer under it. Sending is blocked while loading. */
export function ChatPanel({
  messages,
  loading,
  error,
  emptyText,
  placeholder,
  onSend,
}: ChatPanelProps) {
  const [draft, setDraft] = useState('')

  function handleSend() {
    const text = draft.trim()
    if (!text) return
    setDraft('')
    onSend(text)
  }

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
        />
      </ScrollArea>
      <Composer
        value={draft}
        onChange={setDraft}
        onSend={handleSend}
        disabled={loading}
        placeholder={placeholder}
      />
    </Container>
  )
}
