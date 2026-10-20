import { getJson } from './client.ts'
import type { ConversationOut, MessageOut } from './schema.d.ts'

export type Conversation = ConversationOut

/** One message of a conversation's transcript. */
export type StoredMessage = MessageOut

/** The signed-in user's conversations, the most recently active first. */
export function listConversations(): Promise<Conversation[]> {
  return getJson<Conversation[]>('/api/conversations')
}

/** A conversation's transcript, oldest first. */
export function fetchMessages(
  conversationId: string,
): Promise<StoredMessage[]> {
  return getJson<StoredMessage[]>(
    `/api/conversations/${conversationId}/messages`,
  )
}
