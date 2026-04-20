/* eslint-disable react-refresh/only-export-components */
import { useQuery } from '@tanstack/react-query'
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { clearStoredToken, getMe, getStoredToken, setStoredToken } from '../../lib/api'
import type { MeResponse } from '../../types/qualiflow'

interface AuthContextValue {
  user: MeResponse | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  setToken: (token: string) => void
  logout: () => void
  refetchMe: () => Promise<MeResponse | undefined>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getStoredToken())
  const meQuery = useQuery({
    queryKey: ['me', token],
    queryFn: getMe,
    enabled: Boolean(token),
    retry: false,
  })

  function setToken(nextToken: string) {
    setStoredToken(nextToken)
    setTokenState(nextToken)
  }

  function logout() {
    clearStoredToken()
    setTokenState(null)
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user: meQuery.data ?? null,
      token,
      isAuthenticated: Boolean(token && meQuery.data),
      isLoading: meQuery.isLoading,
      setToken,
      logout,
      refetchMe: async () => (await meQuery.refetch()).data,
    }),
    [meQuery, token],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
