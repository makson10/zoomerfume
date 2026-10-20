import { useEffect, useRef, useState } from 'react'
import {
  streamMessage,
  type Citations,
  type Step,
  type TurnStatus,
} from '../api/chat.ts'
import { ApiError } from '../api/client.ts'
import {
  fetchMessages,
  listConversations,
  type Conversation,
  type StoredMessage,
} from '../api/conversations.ts'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** How Zoomer's reply ended, or `running` while it streams. */
  status?: TurnStatus | null
  /** The tool Zoomer is running right now, while the reply streams. */
  activeTool?: string | null
  /** Set on Zoomer's replies that have a recorded turn. */
  citations?: Citations | null
  steps?: Step[]
}

const FALLBACK_ERROR = "Zoomer couldn't answer right now. Please try again."
const NO_CITATIONS: Citations = { valid: [], invalid: [], missing: false }

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
    status: message.status,
    citations: message.citations,
    steps: message.steps,
  }
}

/**
 * The signed-in user's conversations and the open one.
 *
 * The most recent conversation opens on load. "New chat" only clears the view;
 * the server creates the conversation when its first turn starts. Replies stream in
 * token by token. `stop()` cancels the one in progress, and so does unmounting,
 * for example on log out. A message refused before its turn starts (a rate limit,
 * for example) leaves the chat, and `send()` resolves to `false`, so the composer
 * can give the text back. `notesVersion` goes up each time Zoomer saves a note.
 */
export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notesVersion, setNotesVersion] = useState(0)
  const replyRequest = useRef<AbortController | null>(null)

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

  useEffect(() => () => replyRequest.current?.abort(), [])

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

  async function send(text: string): Promise<boolean> {
    const questionId = crypto.randomUUID()
    const replyId = crypto.randomUUID()
    const updateReply = (
      change: (reply: ChatMessage) => Partial<ChatMessage>,
    ) =>
      setMessages((current) =>
        current.map((message) =>
          message.id === replyId ? { ...message, ...change(message) } : message,
        ),
      )

    const request = new AbortController()
    replyRequest.current = request
    setMessages((current) => [
      ...current,
      { id: questionId, role: 'user', content: text },
      {
        id: replyId,
        role: 'assistant',
        content: '',
        status: 'running',
        steps: [],
      },
    ])
    setError(null)
    setStreaming(true)
    let started = false
    try {
      let done = false
      for await (const chatEvent of streamMessage(
        activeId,
        text,
        request.signal,
      )) {
        switch (chatEvent.event) {
          case 'start':
            started = true
            setActiveId(chatEvent.data.conversation_id)
            listConversations().then(setConversations, () => undefined)
            break
          case 'token':
            updateReply((reply) => ({
              content: reply.content + chatEvent.data.text,
              activeTool: null,
            }))
            break
          case 'tool_call':
            updateReply(() => ({ activeTool: chatEvent.data.tool }))
            break
          case 'tool_result':
            updateReply((reply) => ({
              steps: [...(reply.steps ?? []), chatEvent.data],
              activeTool: null,
            }))
            if (chatEvent.data.tool === 'save_note' && chatEvent.data.success) {
              setNotesVersion((version) => version + 1)
            }
            break
          case 'citation':
            updateReply(() => ({ citations: chatEvent.data }))
            break
          case 'done':
            done = true
            updateReply(() => ({
              content: chatEvent.data.reply,
              status: chatEvent.data.status,
            }))
            break
          case 'error':
            throw new ApiError(500, chatEvent.data.code, chatEvent.data.message)
        }
      }
      if (!done) throw new Error('The reply stream ended early.')
      return true
    } catch (error) {
      const stopped = request.signal.aborted
      const refused = !started && !stopped
      setMessages((current) =>
        current.flatMap((message) => {
          if (refused && message.id === questionId) return []
          if (message.id !== replyId) return [message]
          if (!stopped || !message.content) return []
          return [
            {
              ...message,
              status: 'cancelled',
              activeTool: null,
              citations: NO_CITATIONS,
            },
          ]
        }),
      )
      if (!stopped) setError(errorText(error))
      return !refused
    } finally {
      replyRequest.current = null
      setStreaming(false)
    }
  }

  function stop() {
    replyRequest.current?.abort()
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
    streaming,
    error,
    notesVersion,
    send,
    stop,
    newChat,
    openConversation,
  }
}
