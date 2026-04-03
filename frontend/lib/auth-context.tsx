'use client'

import { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from 'react'
import type { AuthUser } from './types'
import { getMe, login as apiLogin, logout as apiLogout, getToken, clearToken, ApiError } from './api'

interface AuthContextType {
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const checkAuth = useCallback(async (): Promise<boolean> => {
    const token = getToken()
    if (!token) {
      setUser(null)
      setIsLoading(false)
      return false
    }

    try {
      const userData = await getMe()
      setUser(userData)
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearToken()
      }
      setUser(null)
      return false
    } finally {
      setIsLoading(false)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiLogin({ username, password })
    setUser(response.user)
  }, [])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
  }, [])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
