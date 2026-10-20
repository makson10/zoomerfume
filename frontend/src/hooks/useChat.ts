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
 * for example on log out.
 */
export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
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

  async function send(text: string) {
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
      { id: crypto.randomUUID(), role: 'user', content: text },
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
    try {
      let done = false
      for await (const chatEvent of streamMessage(
        activeId,
        text,
        request.signal,
      )) {
        switch (chatEvent.event) {
          case 'start':
            setActiveId(chatEvent.data.conversation_id)
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
    } catch (error) {
      const stopped = request.signal.aborted
      setMessages((current) =>
        current.flatMap((message) => {
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
    } finally {
      replyRequest.current = null
      setStreaming(false)
      listConversations().then(setConversations, () => undefined)
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
    send,
    stop,
    newChat,
    openConversation,
  }
}
