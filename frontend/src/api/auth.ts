import { ApiError, getJson, postJson } from './client.ts'

export interface User {
  id: string
  name: string
  phone_masked: string
}

/** `known` signs the user in; `need_name` asks for a name next. */
export type PhoneResult =
  | { status: 'known'; user: User; message: string }
  | { status: 'need_name'; phone: string; message: string }

export interface SignInResult {
  user: User
  message: string
}

/** Return the signed-in user, or null when nobody is signed in. */
export async function fetchMe(): Promise<User | null> {
  try {
    return await getJson<User>('/api/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** Sign in with a phone number, or learn that the number is new. */
export function signInWithPhone(phone: string): Promise<PhoneResult> {
  return postJson<PhoneResult>('/api/auth/phone', { phone })
}

/** Create an account for a new phone number and sign in. */
export function createAccount(
  phone: string,
  name: string,
): Promise<SignInResult> {
  return postJson<SignInResult>('/api/auth/create', { phone, name })
}

export function logOut(): Promise<void> {
  return postJson<void>('/api/auth/logout')
}
