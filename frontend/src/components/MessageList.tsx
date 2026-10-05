import { Alert, Loader, Stack, Text } from '@mantine/core'
import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../hooks/useChat.ts'
import { MessageBubble } from './MessageBubble.tsx'

interface MessageListProps {
  messages: ChatMessage[]
  loading: boolean
  error: string | null
}

export function MessageList({ messages, loading, error }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, error])

  return (
    <Stack gap="sm" py="md">
      {messages.length === 0 && !loading && (
        <Text c="dimmed" ta="center" pt="xl">
          Hi, I'm Zoomer! Ask me about perfume: notes, seasons, occasions or
          gift ideas.
        </Text>
      )}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      {loading && <Loader type="dots" size="sm" />}
      {error && <Alert color="red">{error}</Alert>}
      <div ref={bottomRef} />
    </Stack>
  )
}
