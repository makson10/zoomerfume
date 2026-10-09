import { getJson, postJson } from './client.ts'

export interface Conversation {
  id: string
  /** Empty until the first message. */
  title: string | null
}

export interface StoredMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
}

/** The signed-in user's conversations, the most recently active first. */
export function listConversations(): Promise<Conversation[]> {
  return getJson<Conversation[]>('/api/conversations')
}

export function createConversation(): Promise<Conversation> {
  return postJson<Conversation>('/api/conversations')
}

/** A conversation's transcript, oldest first. */
export function fetchMessages(
  conversationId: string,
): Promise<StoredMessage[]> {
  return getJson<StoredMessage[]>(
    `/api/conversations/${conversationId}/messages`,
  )
}
