'use client'

import { useEffect, useState, type ReactNode, useCallback, createContext, useContext } from 'react'
import { useRouter } from 'next/navigation'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/app-sidebar'
import { useAuth } from '@/lib/auth-context'
import { useOracleStatus } from '@/hooks/use-oracle-status'
import { Spinner } from '@/components/ui/spinner'
import type { Metadata, HistoryEntry, RuntimeSettings } from '@/lib/types'
import { getMetadata, getHistory, getSettings } from '@/lib/api'

interface AppDataContextType {
  metadata: Metadata | null
  history: HistoryEntry[]
  settings: RuntimeSettings | null
  isLoading: boolean
  refreshMetadata: () => Promise<void>
  refreshHistory: () => Promise<void>
  refreshSettings: () => Promise<void>
  refreshAll: () => Promise<void>
  markOracleActivity: () => void
  startOracleQuery: () => void
  endOracleQuerySuccess: () => void
  endOracleQueryError: () => void
}

const AppDataContext = createContext<AppDataContextType | null>(null)

export function useAppData() {
  const context = useContext(AppDataContext)
  if (!context) {
    throw new Error('useAppData must be used within AppShell')
  }
  return context
}

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter()
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const { status: oracleStatus, checkHealth, markActivity, forceInactive, startQuery, endQuerySuccess, endQueryError } = useOracleStatus()
  
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [settings, setSettings] = useState<RuntimeSettings | null>(null)
  const [dataLoading, setDataLoading] = useState(true)

  const refreshMetadata = useCallback(async () => {
    try {
      const data = await getMetadata()
      setMetadata(data)
      markActivity()
    } catch (error) {
      console.error('[v0] Failed to fetch metadata:', error)
    }
  }, [markActivity])

  const refreshHistory = useCallback(async () => {
    try {
      const data = await getHistory()
      setHistory(data)
    } catch (error) {
      console.error('[v0] Failed to fetch history:', error)
    }
  }, [])

  const refreshSettings = useCallback(async () => {
    try {
      const data = await getSettings()
      setSettings(data)
    } catch (error) {
      console.error('[v0] Failed to fetch settings:', error)
    }
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.all([
      checkHealth(),
      refreshMetadata(),
      refreshHistory(),
      refreshSettings(),
    ])
  }, [checkHealth, refreshMetadata, refreshHistory, refreshSettings])

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Load initial data
  useEffect(() => {
    if (isAuthenticated) {
      setDataLoading(true)
      refreshAll().finally(() => { setDataLoading(false); forceInactive() })
    }
  }, [isAuthenticated, refreshAll, forceInactive])

  // Show loading while checking auth
  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Spinner className="w-8 h-8 text-primary" />
          <p className="text-sm text-muted-foreground">Chargement...</p>
        </div>
      </div>
    )
  }

  // Show loading while fetching initial data
  if (dataLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Spinner className="w-8 h-8 text-primary" />
          <p className="text-sm text-muted-foreground">Chargement des données...</p>
        </div>
      </div>
    )
  }

  return (
    <AppDataContext.Provider
      value={{
        metadata,
        history,
        settings,
        isLoading: dataLoading,
        refreshMetadata,
        refreshHistory,
        refreshSettings,
        refreshAll,
        markOracleActivity: markActivity,
        startOracleQuery: startQuery,
        endOracleQuerySuccess: endQuerySuccess,
        endOracleQueryError: endQueryError,
      }}
    >
      <SidebarProvider>
        <AppSidebar oracleStatus={oracleStatus} />
        <SidebarInset className="bg-background">
          {children}
        </SidebarInset>
      </SidebarProvider>
    </AppDataContext.Provider>
  )
}
