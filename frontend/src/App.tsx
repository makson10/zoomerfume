import { AppShell, Container, ScrollArea } from '@mantine/core'
import { useState } from 'react'
import { Composer } from './components/Composer.tsx'
import { Header } from './components/Header.tsx'
import { MessageList } from './components/MessageList.tsx'
import { useChat } from './hooks/useChat.ts'

export default function App() {
  const { messages, loading, error, send, newChat } = useChat()
  const [draft, setDraft] = useState('')

  function handleSend() {
    const text = draft.trim()
    if (!text) return
    setDraft('')
    void send(text)
  }

  return (
    <AppShell header={{ height: 60 }}>
      <AppShell.Header>
        <Header onNewChat={newChat} newChatDisabled={loading} />
      </AppShell.Header>
      <AppShell.Main h="100dvh">
        <Container
          size="sm"
          h="100%"
          style={{ display: 'flex', flexDirection: 'column' }}
        >
          <ScrollArea flex={1} mih={0}>
            <MessageList messages={messages} loading={loading} error={error} />
          </ScrollArea>
          <Composer
            value={draft}
            onChange={setDraft}
            onSend={handleSend}
            disabled={loading}
          />
        </Container>
      </AppShell.Main>
    </AppShell>
  )
}
