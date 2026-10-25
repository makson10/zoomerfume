import {
  ActionIcon,
  AppShell,
  Box,
  Burger,
  Button,
  Text,
  type MantineBreakpoint,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconLogout,
  IconNotes,
  IconTool,
  type TablerIcon,
} from '@tabler/icons-react'
import { useState } from 'react'
import type { User } from '../api/auth.ts'
import { useChat } from '../hooks/useChat.ts'
import { ChatPanel } from './ChatPanel.tsx'
import { ConversationList } from './ConversationList.tsx'
import { Header } from './Header.tsx'
import { ModeBadge } from './ModeBadge.tsx'
import { NotesPanel } from './NotesPanel.tsx'
import { RecordDrawer } from './RecordDrawer.tsx'
import { ToolsModal } from './ToolsModal.tsx'

interface HeaderButtonProps {
  label: string
  icon: TablerIcon
  onClick: () => void
  active?: boolean
  /** Hides the button from this breakpoint on. */
  hiddenFrom?: MantineBreakpoint
}

/** A header button with a label on wider screens and only its icon on phones. */
function HeaderButton({
  label,
  icon: Icon,
  onClick,
  active = false,
  hiddenFrom,
}: HeaderButtonProps) {
  const variant = active ? 'light' : 'default'
  return (
    <>
      <Button
        variant={variant}
        leftSection={<Icon size={16} />}
        onClick={onClick}
        visibleFrom="sm"
        hiddenFrom={hiddenFrom}
      >
        {label}
      </Button>
      <ActionIcon
        variant={variant}
        size="input-sm"
        onClick={onClick}
        hiddenFrom="sm"
        aria-label={label}
      >
        <Icon size={18} />
      </ActionIcon>
    </>
  )
}

interface ChatPageProps {
  user: User
  greeting: string | null
  onLogOut: () => void
}

/**
 * The signed-in page: conversations on the left, the open chat in the middle and the
 * notes on the right. On smaller screens the side panels fold away.
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
              <Box visibleFrom="md">
                <ModeBadge security={user.security} />
              </Box>
              <Text size="sm" visibleFrom="sm">
                {user.name}
              </Text>
              <HeaderButton
                label="Notes"
                icon={IconNotes}
                onClick={toggleNotes}
                active={notesOpened}
                hiddenFrom="md"
              />
              <HeaderButton
                label="Tools"
                icon={IconTool}
                onClick={tools.open}
              />
              <HeaderButton
                label="Log out"
                icon={IconLogout}
                onClick={onLogOut}
              />
            </>
          }
        />
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <Box hiddenFrom="md" pb="xs">
          <ModeBadge security={user.security} />
        </Box>
        <ConversationList
          conversations={chat.conversations}
          activeId={chat.activeId}
          disabled={chat.loading || chat.streaming}
          onSelect={openConversation}
          onNewChat={newChat}
        />
      </AppShell.Navbar>
      <AppShell.Aside p="sm">
        <NotesPanel refreshKey={chat.notesVersion} onDecide={chat.decideNote} />
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
          onDecideNote={chat.decideNote}
        />
      </AppShell.Main>
      <RecordDrawer recordId={recordId} onClose={() => setRecordId(null)} />
      <ToolsModal opened={toolsOpened} onClose={tools.close} />
    </AppShell>
  )
}
