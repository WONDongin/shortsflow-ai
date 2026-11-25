// 영상 업로드·조회·추출·다운로드 화면
import { useEffect, useState, type FormEvent } from 'react'

// API 주소 설정, 기본값은 로컬 FastAPI 주소
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const statusLabels = {
  checking: '백엔드 연결 확인 중',
  connected: '백엔드 연결 정상',
  unavailable: '백엔드 연결 실패',
}

// 영상 조회 응답 타입
type Video = {
  video_id: string
  size_bytes: number
  metadata: {
    duration_seconds: number
    width: number
    height: number
    fps: number
    video_codec: string
    has_audio: boolean
  }
  audio_path: string | null
  frame_path: string | null
}

const videosUrl = `${apiBaseUrl}/api/videos`
const downloads = {
  source: { label: '원본 MP4', filename: 'source.mp4' },
  audio: { label: '음성 WAV', filename: 'audio.wav' },
  frame: { label: '프레임 JPG', filename: 'frame.jpg' },
}

// API 요청 및 실패 응답 메시지 처리
async function request(url: string, init?: RequestInit) {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.[0]?.msg
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return response
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '요청을 완료하지 못했습니다.'
}

function videoUrl(videoId: string) {
  return `${videosUrl}/${encodeURIComponent(videoId)}`
}

function App() {
  const [status, setStatus] = useState<keyof typeof statusLabels>('checking')
  const [initialId] = useState(() => new URLSearchParams(window.location.search).get('video') || '')
  const [lookupId, setLookupId] = useState(initialId)
  const [video, setVideo] = useState<Video | null>(null)
  const [busy, setBusy] = useState(initialId ? '영상 조회' : '')
  const [error, setError] = useState('')

  // 새로고침 시 URL의 UUID로 영상 재조회
  useEffect(() => {
    if (!initialId) return
    const controller = new AbortController()
    void (async () => {
      try {
        const response = await request(videoUrl(initialId), { signal: controller.signal })
        const result: Video = await response.json()
        if (!controller.signal.aborted) setVideo(result)
      } catch (error) {
        if (!controller.signal.aborted) setError(`영상 조회 실패 · ${errorMessage(error)}`)
      } finally {
        if (!controller.signal.aborted) setBusy('')
      }
    })()
    return () => controller.abort()
  }, [initialId])

  // 앱 실행 시 FastAPI 연결 상태 확인
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

  // 선택한 영상 표시 및 URL에 UUID 저장
  function selectVideo(result: Video) {
    setVideo(result)
    setLookupId(result.video_id)
    const url = new URL(window.location.href)
    url.searchParams.set('video', result.video_id)
    window.history.replaceState(null, '', url)
  }

  // 요청 중 입력 비활성화 및 실패 메시지 표시
  async function run(label: string, action: () => Promise<void>) {
    setBusy(label)
    setError('')
    try {
      await action()
    } catch (error) {
      setError(`${label} 실패 · ${errorMessage(error)}`)
    } finally {
      setBusy('')
    }
  }

  // MP4를 multipart/form-data로 업로드
  function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = new FormData(event.currentTarget)
    void run('MP4 업로드', async () => {
      const response = await request(videosUrl, { method: 'POST', body })
      selectVideo(await response.json())
    })
  }

  // 입력한 UUID로 영상과 결과물 조회
  function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run('영상 조회', async () => {
      const response = await request(videoUrl(lookupId.trim()))
      selectVideo(await response.json())
    })
  }

  // 음성·프레임 추출 후 결과물 경로 반영
  function extract(current: Video, kind: 'audio' | 'frame', seconds?: string) {
    const query = seconds === undefined ? '' : `?timestamp_seconds=${encodeURIComponent(seconds)}`
    void run(kind === 'audio' ? '음성 추출' : '프레임 추출', async () => {
      const field = kind === 'audio' ? 'audio_path' : 'frame_path'
      const response = await request(`${videoUrl(current.video_id)}/extract-${kind}${query}`, { method: 'POST' })
      const result: { path: string } = await response.json()
      setVideo({ ...current, [field]: result.path })
    })
  }

  // 브라우저 다운로드 시작 후 임시 URL 해제
  function download(current: Video, kind: keyof typeof downloads) {
    const { label, filename } = downloads[kind]
    void run(`${label} 다운로드`, async () => {
      const response = await request(`${videoUrl(current.video_id)}/download/${kind}`)
      const objectUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = filename
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    })
  }

  return (
    <main>
      <h1>ShortsFlow AI</h1>
      <p role="status">{statusLabels[status]}</p>
      <p role="status">{busy && `${busy} 중…`}</p>
      {error && <p role="alert">{error}</p>}

      {/* MP4 업로드와 UUID 조회 영역 */}
      <section aria-labelledby="video-input">
        <h2 id="video-input">영상 열기</h2>
        <form onSubmit={upload}>
          <label htmlFor="video-file">MP4 파일</label>
          <div className="controls">
            <input id="video-file" name="file" type="file" accept=".mp4,video/mp4" required disabled={!!busy} />
            <button disabled={!!busy}>업로드</button>
          </div>
        </form>
        <form onSubmit={lookup}>
          <label htmlFor="video-id">영상 UUID</label>
          <div className="controls">
            <input id="video-id" type="text" value={lookupId} required disabled={!!busy}
              onChange={(event) => setLookupId(event.target.value)} />
            <button disabled={!!busy}>조회</button>
          </div>
        </form>
      </section>

      {/* 영상 정보와 추출·다운로드 버튼 */}
      {video && (
        <section aria-labelledby="video-details" key={video.video_id}>
          <h2 id="video-details">영상 정보</h2>
          <dl>
            <dt>UUID</dt><dd>{video.video_id}</dd>
            <dt>파일 크기</dt><dd>{video.size_bytes.toLocaleString()} 바이트</dd>
            <dt>길이</dt><dd>{video.metadata.duration_seconds.toLocaleString()}초</dd>
            <dt>해상도</dt><dd>{video.metadata.width} × {video.metadata.height}</dd>
            <dt>프레임률</dt><dd>{video.metadata.fps.toLocaleString()} fps</dd>
            <dt>코덱</dt><dd>{video.metadata.video_codec}</dd>
            <dt>음성 트랙</dt><dd>{video.metadata.has_audio ? '있음' : '없음'}</dd>
          </dl>
          <h2>결과물</h2>
          <div className="controls">
            <button type="button" disabled={!!busy} onClick={() => download(video, 'source')}>원본 MP4 다운로드</button>
          </div>
          <div className="controls">
            <button type="button" disabled={!!busy || !video.metadata.has_audio} onClick={() => extract(video, 'audio')}>음성 추출</button>
            <button type="button" disabled={!!busy || !video.audio_path} onClick={() => download(video, 'audio')}>WAV 다운로드</button>
          </div>
          <form onSubmit={(event) => {
            event.preventDefault()
            const seconds = String(new FormData(event.currentTarget).get('seconds'))
            extract(video, 'frame', seconds)
          }}>
            <label htmlFor="frame-seconds">프레임 추출 시점 (초)</label>
            <div className="controls">
              <input id="frame-seconds" name="seconds" type="number" min="0" step="any" defaultValue="0" required disabled={!!busy} />
              <button disabled={!!busy}>프레임 추출</button>
              <button type="button" disabled={!!busy || !video.frame_path} onClick={() => download(video, 'frame')}>JPG 다운로드</button>
            </div>
          </form>
        </section>
      )}
    </main>
  )
}

export default App
