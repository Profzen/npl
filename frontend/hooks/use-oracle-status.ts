'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import type { OracleStatus } from '@/lib/types'
import { getHealth } from '@/lib/api'

const INACTIVE_TIMEOUT = 30000 // 30 seconds

export function useOracleStatus() {
  const [status, setStatus] = useState<OracleStatus>('disconnected')
  const [isChecking, setIsChecking] = useState(false)
  const lastActivityRef = useRef<number>(Date.now())
  const inactivityTimerRef = useRef<NodeJS.Timeout | null>(null)
  const statusRef = useRef<OracleStatus>('disconnected')
  // Blocks inactivity timeout while a query is running
  const isQueryRunningRef = useRef(false)

  useEffect(() => {
    statusRef.current = status
  }, [status])

  const checkHealth = useCallback(async () => {
    setIsChecking(true)
    try {
      const health = await getHealth()
      if (health.oracle === 'connected') {
        setStatus('connected')
        lastActivityRef.current = Date.now()
      } else {
        setStatus('disconnected')
      }
    } catch {
      setStatus('disconnected')
    } finally {
      setIsChecking(false)
    }
  }, [])

  const markActivity = useCallback(() => {
    lastActivityRef.current = Date.now()
    if (statusRef.current === 'inactive') {
      void checkHealth()
    }
  }, [checkHealth])

  // Called after initial data load — go orange (inactive) if Oracle was connected
  const forceInactive = useCallback(() => {
    setStatus((current) => (current === 'connected' ? 'inactive' : current))
  }, [])

  // Called when a query starts — go green immediately, block inactivity timer
  const startQuery = useCallback(() => {
    isQueryRunningRef.current = true
    setStatus('connected')
    lastActivityRef.current = Date.now()
  }, [])

  // Called when query succeeds — stay green, reset inactivity timer
  const endQuerySuccess = useCallback(() => {
    isQueryRunningRef.current = false
    lastActivityRef.current = Date.now()
  }, [])

  // Called when query fails — go red
  const endQueryError = useCallback(() => {
    isQueryRunningRef.current = false
    setStatus('disconnected')
  }, [])

  // Check for inactivity — skipped while a query is running
  useEffect(() => {
    const checkInactivity = () => {
      if (status === 'connected' && !isQueryRunningRef.current) {
        const elapsed = Date.now() - lastActivityRef.current
        if (elapsed >= INACTIVE_TIMEOUT) {
          setStatus('inactive')
        }
      }
    }

    inactivityTimerRef.current = setInterval(checkInactivity, 5000)

    return () => {
      if (inactivityTimerRef.current) {
        clearInterval(inactivityTimerRef.current)
      }
    }
  }, [status])

  return {
    status,
    isChecking,
    checkHealth,
    markActivity,
    forceInactive,
    startQuery,
    endQuerySuccess,
    endQueryError,
  }
}
