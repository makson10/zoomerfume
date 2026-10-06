import { useEffect, useState } from 'react'
import { fetchMe, logOut as postLogOut, type User } from '../api/auth.ts'

/**
 * The signed-in user, checked once on load.
 *
 * `user` is undefined while the check runs and null when nobody is signed in.
 * `greeting` is Zoomer's line from a sign-in in this tab.
 */
export function useSession() {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [greeting, setGreeting] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    fetchMe().then(
      (me) => {
        if (!ignore) setUser(me)
      },
      () => {
        if (!ignore) setUser(null)
      },
    )
    return () => {
      ignore = true
    }
  }, [])

  function signedIn(user: User, message: string) {
    setUser(user)
    setGreeting(message)
  }

  async function logOut() {
    try {
      await postLogOut()
    } finally {
      setUser(null)
      setGreeting(null)
    }
  }

  return { user, greeting, signedIn, logOut }
}
