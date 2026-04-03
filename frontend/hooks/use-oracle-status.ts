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

  // Check for inactivity
  useEffect(() => {
    const checkInactivity = () => {
      if (status === 'connected') {
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
  }
}
