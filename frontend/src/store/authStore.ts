import { create } from 'zustand'
import type { AuthUser } from '../types'
import { clearToken, getToken, setToken, login as apiLogin, getMe } from '../lib/api'

interface AuthStore {
  user: AuthUser | null
  token: string | null
  loading: boolean
  error: string | null

  // Actions
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  restoreSession: () => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: getToken(),
  // If a token exists we start in loading state so the app never flashes the
  // login page before restoreSession has a chance to verify it.
  loading: !!getToken(),
  error: null,

  login: async (username, password) => {
    // Clear any stale token before attempting login
    clearToken()
    set({ error: null, token: null })
    try {
      const resp = await apiLogin(username, password)
      setToken(resp.access_token)
      const user = await getMe()
      set({ user, token: resp.access_token })
    } catch (err: any) {
      clearToken()
      set({ user: null, token: null })
      throw err
    }
  },

  logout: () => {
    clearToken()
    set({ user: null, token: null, error: null })
  },

  restoreSession: async () => {
    const token = getToken()
    if (!token) return
    set({ loading: true })
    try {
      const user = await getMe()
      set({ user, loading: false })
    } catch {
      clearToken()
      set({ user: null, token: null, loading: false })
    }
  },
}))
