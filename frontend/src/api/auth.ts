import { ApiError, getJson, postJson } from './client.ts'
import type {
  CreateUserRequest,
  KnownPhone,
  NewPhone,
  PhoneRequest,
  SecurityPolicy,
  SignInResponse,
  UserOut,
} from './schema.d.ts'

export type { SecurityPolicy }

/** The signed-in user, with the security mode the server runs in. */
export type User = UserOut

/** `known` signs the user in; `need_name` asks for a name next. */
export type PhoneResult = KnownPhone | NewPhone

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
  return postJson<PhoneResult>('/api/auth/phone', {
    phone,
  } satisfies PhoneRequest)
}

/** Create an account for a new phone number and sign in. */
export function createAccount(
  phone: string,
  name: string,
): Promise<SignInResponse> {
  return postJson<SignInResponse>('/api/auth/create', {
    phone,
    name,
  } satisfies CreateUserRequest)
}

export function logOut(): Promise<void> {
  return postJson<void>('/api/auth/logout')
}
