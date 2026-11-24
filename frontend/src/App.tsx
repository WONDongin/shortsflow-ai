import { useEffect, useState } from 'react'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const statusLabels = {
  checking: '백엔드 연결 확인 중',
  connected: '백엔드 연결 정상',
  unavailable: '백엔드 연결 실패',
}

function App() {
  const [status, setStatus] = useState<keyof typeof statusLabels>('checking')

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/health`, { signal: controller.signal })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const data: { status?: unknown } = await response.json()
        if (!controller.signal.aborted) {
          setStatus(data?.status === 'ok' ? 'connected' : 'unavailable')
        }
      } catch {
        if (!controller.signal.aborted) setStatus('unavailable')
      }
    }

    void checkHealth()
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>ShortsFlow AI</h1>
      <p role="status">{statusLabels[status]}</p>
    </main>
  )
}

export default App
