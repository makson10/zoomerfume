import { AppShell, Center, Loader } from '@mantine/core'
import { ChatPage } from './components/ChatPage.tsx'
import { Header } from './components/Header.tsx'
import { SignInFlow } from './components/SignInFlow.tsx'
import { useSession } from './hooks/useSession.ts'

export default function App() {
  const { user, greeting, signedIn, logOut } = useSession()

  if (user === undefined) {
    return (
      <Center h="100dvh">
        <Loader type="dots" />
      </Center>
    )
  }

  if (user === null) {
    return (
      <AppShell header={{ height: 60 }}>
        <AppShell.Header>
          <Header />
        </AppShell.Header>
        <AppShell.Main h="100dvh">
          <SignInFlow onSignedIn={signedIn} />
        </AppShell.Main>
      </AppShell>
    )
  }

  return (
    <ChatPage
      key={user.id}
      user={user}
      greeting={greeting}
      onLogOut={() => void logOut()}
    />
  )
}
