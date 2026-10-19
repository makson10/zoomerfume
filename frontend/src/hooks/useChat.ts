import { useEffect, useState } from 'react'
import { sendMessage, type Citations, type Step } from '../api/chat.ts'
import { ApiError } from '../api/client.ts'
import {
  createConversation,
  fetchMessages,
  listConversations,
  type Conversation,
  type StoredMessage,
} from '../api/conversations.ts'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** Set on Zoomer's replies that have a recorded turn. */
  citations?: Citations | null
  steps?: Step[]
}

const FALLBACK_ERROR = "Zoomer couldn't answer right now. Please try again."

function errorText(error: unknown): string {
  return error instanceof ApiError && error.code
    ? error.message
    : FALLBACK_ERROR
}

function toChatMessage(message: StoredMessage): ChatMessage {
  return {
    id: String(message.id),
    role: message.role,
    content: message.content,
    citations: message.citations,
    steps: message.steps,
  }
}

/**
 * The signed-in user's conversations and the open one.
 *
 * The most recent conversation opens on load. "New chat" only clears the view;
 * the conversation is created when its first message is sent.
 */
export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    listConversations().then(
      (list) => {
        if (ignore) return
        setConversations(list)
        if (list.length > 0) {
          void openConversation(list[0].id)
        } else {
          setLoading(false)
        }
      },
      (error) => {
        if (ignore) return
        setError(errorText(error))
        setLoading(false)
      },
    )
    return () => {
      ignore = true
    }
  }, [])

  async function openConversation(id: string) {
    setActiveId(id)
    setMessages([])
    setError(null)
    setLoading(true)
    try {
      const stored = await fetchMessages(id)
      setMessages(stored.map(toChatMessage))
    } catch (error) {
      setError(errorText(error))
    } finally {
      setLoading(false)
    }
  }

  async function send(text: string) {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: text },
    ])
    setError(null)
    setLoading(true)
    try {
      const id = activeId ?? (await createConversation()).id
      setActiveId(id)
      const { reply, citations, steps } = await sendMessage(id, text)
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: reply,
          citations,
          steps,
        },
      ])
      listConversations().then(setConversations, () => undefined)
    } catch (error) {
      setError(errorText(error))
    } finally {
      setLoading(false)
    }
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
    setError(null)
  }

  return {
    conversations,
    activeId,
    messages,
    loading,
    error,
    send,
    newChat,
    openConversation,
  }
}
