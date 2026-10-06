import { useState } from 'react'
import { createAccount, signInWithPhone, type User } from '../api/auth.ts'
import { ApiError } from '../api/client.ts'
import type { ChatMessage } from '../hooks/useChat.ts'
import { ChatPanel } from './ChatPanel.tsx'

const FIRST_QUESTION =
  "Hi, I'm Zoomer, your perfume buddy! To get started, what's your phone number?"
const FALLBACK_ERROR =
  'Something went wrong on my side. Please try again in a minute.'

function chatLine(role: ChatMessage['role'], content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content }
}

interface SignInFlowProps {
  onSignedIn: (user: User, greeting: string) => void
}

/**
 * Zoomer's scripted sign-in chat: the phone number first, then a name if the
 * number is new. Every line from Zoomer after the first comes from the API.
 */
export function SignInFlow({ onSignedIn }: SignInFlowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    chatLine('assistant', FIRST_QUESTION),
  ])
  const [newPhone, setNewPhone] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSend(text: string) {
    setMessages((current) => [...current, chatLine('user', text)])
    setLoading(true)
    try {
      if (newPhone === null) {
        const result = await signInWithPhone(text)
        if (result.status === 'known') {
          onSignedIn(result.user, result.message)
          return
        }
        setNewPhone(result.phone)
        setMessages((current) => [
          ...current,
          chatLine('assistant', result.message),
        ])
      } else {
        const result = await createAccount(newPhone, text)
        onSignedIn(result.user, result.message)
      }
    } catch (error) {
      const message =
        error instanceof ApiError && error.code ? error.message : FALLBACK_ERROR
      setMessages((current) => [...current, chatLine('assistant', message)])
    } finally {
      setLoading(false)
    }
  }

  return (
    <ChatPanel
      messages={messages}
      loading={loading}
      error={null}
      placeholder={newPhone === null ? 'Your phone number' : 'Your name'}
      onSend={(text) => void handleSend(text)}
    />
  )
}
