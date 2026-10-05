import { useEffect, useState } from 'react'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

interface ChatResponse {
  reply: string
}

const SESSION_KEY = 'zoomerfume:session-id'

/**
 * Chat state for one session with Zoomer.
 *
 * The session id is kept in localStorage, and "New chat" replaces it with a fresh one.
 */
export function useChat() {
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem(SESSION_KEY) ?? crypto.randomUUID(),
  )
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, sessionId)
  }, [sessionId])

  async function send(text: string) {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: text },
    ])
    setError(null)
    setLoading(true)
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      })
      if (!response.ok) {
        throw new Error(`POST /api/chat failed with ${response.status}`)
      }
      const data: ChatResponse = await response.json()
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: 'assistant', content: data.reply },
      ])
    } catch {
      setError("Zoomer couldn't answer right now. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  function newChat() {
    setSessionId(crypto.randomUUID())
    setMessages([])
    setError(null)
  }

  return { messages, loading, error, send, newChat }
}
