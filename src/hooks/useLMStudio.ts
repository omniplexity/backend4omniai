import { useCallback, useEffect, useRef } from 'react'
import { lmStudioClient } from '../lib/lmstudio'
import { useConnectionStore } from '../stores/connection'
import { useSettingsStore } from '../stores/settings'
import type { ModelInfo } from '../types/model'

const HEALTH_CHECK_INTERVAL = 30_000 // 30 seconds
const RETRY_DELAY = 5_000 // 5 seconds

export function useLMStudio() {
  const lmStudioUrl = useSettingsStore((s) => s.lmStudioUrl)
  const { status, error, models, selectedModel, setStatus, setModels, selectModel } =
    useConnectionStore()

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /** Fetch available models from LM Studio */
  const fetchModels = useCallback(async (): Promise<ModelInfo[]> => {
    try {
      const response = await lmStudioClient.listModels()
      return response.data.map((m) => ({
        id: m.id,
        name: m.id.split('/').pop() || m.id, // Extract model name from path
      }))
    } catch {
      return []
    }
  }, [])

  /** Check connection and update status */
  const checkConnection = useCallback(async () => {
    setStatus('connecting')

    const health = await lmStudioClient.healthCheck()

    if (health.ok) {
      const modelList = await fetchModels()
      setModels(modelList)
      setStatus('connected')
    } else {
      setStatus('error', health.error)

      // Schedule retry
      retryTimeoutRef.current = setTimeout(checkConnection, RETRY_DELAY)
    }
  }, [fetchModels, setModels, setStatus])

  /** Manually trigger reconnection */
  const reconnect = useCallback(() => {
    // Clear any pending retry
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    checkConnection()
  }, [checkConnection])

  // Initialize connection and set up periodic health checks
  useEffect(() => {
    // Update client URL
    lmStudioClient.setBaseUrl(lmStudioUrl)

    // Initial connection check
    checkConnection()

    // Set up periodic health checks
    intervalRef.current = setInterval(() => {
      lmStudioClient.healthCheck().then((health) => {
        if (!health.ok) {
          setStatus('error', health.error)
        }
      })
    }, HEALTH_CHECK_INTERVAL)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current)
      }
    }
    // Only re-run when URL changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lmStudioUrl])

  return {
    status,
    error,
    models,
    selectedModel,
    selectModel,
    reconnect,
    isConnected: status === 'connected',
    isConnecting: status === 'connecting',
  }
}
