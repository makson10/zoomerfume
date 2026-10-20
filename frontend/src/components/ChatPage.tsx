import { ActionIcon, AppShell, Burger, Button, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconLogout, IconNotes, IconTool } from '@tabler/icons-react'
import { useState } from 'react'
import type { User } from '../api/auth.ts'
import { useChat } from '../hooks/useChat.ts'
import { ChatPanel } from './ChatPanel.tsx'
import { ConversationList } from './ConversationList.tsx'
import { Header } from './Header.tsx'
import { NotesPanel } from './NotesPanel.tsx'
import { RecordDrawer } from './RecordDrawer.tsx'
import { ToolsModal } from './ToolsModal.tsx'

interface ChatPageProps {
  user: User
  greeting: string | null
  onLogOut: () => void
}

/**
 * The signed-in page: conversations on the left, the open chat in the middle and the
 * customer's notes on the right. Cited records open in a drawer, and the header shows
 * the tool schemas. On smaller screens the conversations and the notes fold away.
 */
export function ChatPage({ user, greeting, onLogOut }: ChatPageProps) {
  const chat = useChat()
  const [navbarOpened, navbar] = useDisclosure()
  const [notesOpened, notes] = useDisclosure()
  const [toolsOpened, tools] = useDisclosure()
  const [recordId, setRecordId] = useState<string | null>(null)

  function toggleNavbar() {
    notes.close()
    navbar.toggle()
  }

  function toggleNotes() {
    navbar.close()
    notes.toggle()
  }

  function openConversation(id: string) {
    navbar.close()
    void chat.openConversation(id)
  }

  function newChat() {
    navbar.close()
    chat.newChat()
  }

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 260,
        breakpoint: 'sm',
        collapsed: { mobile: !navbarOpened },
      }}
      aside={{
        width: 280,
        breakpoint: 'md',
        collapsed: { mobile: !notesOpened },
      }}
    >
      <AppShell.Header>
        <Header
          burger={
            <Burger
              opened={navbarOpened}
              onClick={toggleNavbar}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle chats"
            />
          }
          actions={
            <>
              <Text size="sm" visibleFrom="sm">
                {user.name}
              </Text>
              <Button
                variant={notesOpened ? 'light' : 'default'}
                leftSection={<IconNotes size={16} />}
                onClick={toggleNotes}
                visibleFrom="sm"
                hiddenFrom="md"
              >
                Notes
              </Button>
              <ActionIcon
                variant={notesOpened ? 'light' : 'default'}
                size="input-sm"
                onClick={toggleNotes}
                hiddenFrom="sm"
                aria-label="Notes"
              >
                <IconNotes size={18} />
              </ActionIcon>
              <Button
                variant="default"
                leftSection={<IconTool size={16} />}
                onClick={tools.open}
                visibleFrom="sm"
              >
                Tools
              </Button>
              <ActionIcon
                variant="default"
                size="input-sm"
                onClick={tools.open}
                hiddenFrom="sm"
                aria-label="Tools"
              >
                <IconTool size={18} />
              </ActionIcon>
              <Button
                variant="default"
                leftSection={<IconLogout size={16} />}
                onClick={onLogOut}
                visibleFrom="sm"
              >
                Log out
              </Button>
              <ActionIcon
                variant="default"
                size="input-sm"
                onClick={onLogOut}
                hiddenFrom="sm"
                aria-label="Log out"
              >
                <IconLogout size={18} />
              </ActionIcon>
            </>
          }
        />
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <ConversationList
          conversations={chat.conversations}
          activeId={chat.activeId}
          disabled={chat.loading || chat.streaming}
          onSelect={openConversation}
          onNewChat={newChat}
        />
      </AppShell.Navbar>
      <AppShell.Aside p="sm">
        <NotesPanel refreshKey={chat.notesVersion} />
      </AppShell.Aside>
      <AppShell.Main h="100dvh">
        <ChatPanel
          messages={chat.messages}
          loading={chat.loading}
          streaming={chat.streaming}
          error={chat.error}
          emptyText={
            greeting ??
            `Hi, ${user.name}! Ask me about our perfumes, prices, delivery or returns, or anything about perfume.`
          }
          onSend={chat.send}
          onStop={chat.stop}
          onOpenRecord={setRecordId}
        />
      </AppShell.Main>
      <RecordDrawer recordId={recordId} onClose={() => setRecordId(null)} />
      <ToolsModal opened={toolsOpened} onClose={tools.close} />
    </AppShell>
  )
}
