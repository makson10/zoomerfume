import { AppShell, Burger, Button, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconLogout } from '@tabler/icons-react'
import type { User } from '../api/auth.ts'
import { useChat } from '../hooks/useChat.ts'
import { ChatPanel } from './ChatPanel.tsx'
import { ConversationList } from './ConversationList.tsx'
import { Header } from './Header.tsx'

interface ChatPageProps {
  user: User
  greeting: string | null
  onLogOut: () => void
}

/** The signed-in page: conversations on the left, the open chat in the middle. */
export function ChatPage({ user, greeting, onLogOut }: ChatPageProps) {
  const chat = useChat()
  const [navbarOpened, navbar] = useDisclosure()

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
    >
      <AppShell.Header>
        <Header
          burger={
            <Burger
              opened={navbarOpened}
              onClick={navbar.toggle}
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
                variant="default"
                leftSection={<IconLogout size={16} />}
                onClick={onLogOut}
              >
                Log out
              </Button>
            </>
          }
        />
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <ConversationList
          conversations={chat.conversations}
          activeId={chat.activeId}
          disabled={chat.loading}
          onSelect={openConversation}
          onNewChat={newChat}
        />
      </AppShell.Navbar>
      <AppShell.Main h="100dvh">
        <ChatPanel
          messages={chat.messages}
          loading={chat.loading}
          error={chat.error}
          emptyText={
            greeting ??
            `Hi, ${user.name}! Ask me about perfume: notes, seasons, occasions or gift ideas.`
          }
          onSend={(text) => void chat.send(text)}
        />
      </AppShell.Main>
    </AppShell>
  )
}
