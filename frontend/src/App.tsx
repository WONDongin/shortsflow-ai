// 영상 업로드, 자동 편집 진행, 결과물 조회·다운로드 화면
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Icon } from './Icon'

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
  transcript_path: string | null
}

type Transcript = {
  video_id: string
  language: string
  segments: { start_seconds: number; end_seconds: number; text: string }[]
}

const videosUrl = `${apiBaseUrl}/api/videos`
// 수동 다운로드 종류별 표시명과 파일명
const downloads = {
  source: { label: '원본 MP4', filename: 'source.mp4' },
  audio: { label: '음성 WAV', filename: 'audio.wav' },
  frame: { label: '프레임 JPG', filename: 'frame.jpg' },
  transcript: { label: '자막 JSON', filename: 'transcript.json' },
}

const segmentTime = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 6 })

// 워크플로우 단계별 팝업 문구와 응답 타입
const workflowLabels = {
  queued: '영상 업로드 및 정보 저장 중',
  extracting: '음성 추출 중',
  transcribing: '자막 생성 중',
  analyzing: '쇼츠 구간 분석 중',
  rendering: '영상 편집 및 자막 합성 중',
  completed: '영상 편집 완료!',
  no_candidate: '쇼츠 후보 없음',
  failed: '영상 처리 실패',
}

type Workflow = {
  video_id: string
  stage: keyof typeof workflowLabels
  analysis_id: string | null
  error: string | null
}

const progressSteps = ['queued', 'extracting', 'transcribing', 'analyzing', 'rendering'] as const

function workflowFinished(workflow: Workflow) {
  return ['completed', 'no_candidate', 'failed'].includes(workflow.stage)
}

// API 오류 메시지와 HTTP 상태 코드 보관
class RequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// API 요청 및 실패 응답 메시지 처리
async function request(url: string, init?: RequestInit) {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.[0]?.msg
    throw new RequestError(detail || `HTTP ${response.status}`, response.status)
  }
  return response
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '요청을 완료하지 못했습니다.'
}

function videoUrl(videoId: string) {
  return `${videosUrl}/${encodeURIComponent(videoId)}`
}

// 자막 파일이 있는 영상의 자막 조회
async function loadTranscript(video: Video, signal?: AbortSignal): Promise<Transcript | null> {
  if (!video.transcript_path) return null
  const response = await request(`${videoUrl(video.video_id)}/transcript`, { signal })
  return response.json()
}

// 영상 UUID로 워크플로우 상태 조회
async function loadWorkflow(videoId: string, signal?: AbortSignal): Promise<Workflow | null> {
  try {
    const response = await request(`${videoUrl(videoId)}/workflow`, { signal })
    return response.json()
  } catch (error) {
    if (error instanceof RequestError && error.status === 404) return null
    throw error
  }
}

// 완료·실패·후보 없음까지 워크플로우 상태 주기 조회
async function followWorkflow(
  initial: Workflow, onProgress: (workflow: Workflow) => void, signal?: AbortSignal,
) {
  let current = initial
  while (!signal?.aborted) {
    onProgress(current)
    if (workflowFinished(current)) return
    await new Promise((resolve) => window.setTimeout(resolve, 750))
    if (signal?.aborted) return
    const next = await loadWorkflow(initial.video_id, signal)
    if (!next) throw new Error('영상 처리 상태를 찾을 수 없습니다.')
    current = next
  }
}

// 진행 단계와 실패 원인을 표시하는 팝업
function WorkflowDialog({ workflow, error, close }: {
  workflow: Workflow | null
  error: string
  close: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const finished = !!error || (workflow !== null && workflowFinished(workflow))
  const reason = error || workflow?.error
  const complete = !error && workflow?.stage === 'completed'
  const activeStep = progressSteps.findIndex((step) => step === (workflow?.stage ?? 'queued'))

  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog className="workflow-dialog" ref={ref} aria-labelledby="workflow-progress" onCancel={(event) => {
      event.preventDefault()
      if (finished) close()
    }}>
      <span className={`dialog-symbol ${!finished ? 'is-running' : ''}`}>
        <Icon name={finished ? (complete ? 'check' : 'alert') : 'spark'} />
      </span>
      <h2 id="workflow-progress" role="status">
        {error ? workflowLabels.failed : workflowLabels[workflow?.stage ?? 'queued']}
      </h2>
      {reason && <p className="dialog-reason" role="alert">{reason}</p>}
      {!finished && (
        <div className="workflow-track" aria-hidden="true">
          {progressSteps.map((step, index) => <span key={step} data-reached={index <= activeStep} />)}
        </div>
      )}
      {finished && <button className="button button--primary" type="button" onClick={close}>닫기</button>}
    </dialog>
  )
}

// 영상 선택과 편집 작업 화면 상태 관리
function App() {
  const [status, setStatus] = useState<keyof typeof statusLabels>('checking')
  const [initialId] = useState(() => new URLSearchParams(window.location.search).get('video') || '')
  const [lookupId, setLookupId] = useState(initialId)
  const [fileName, setFileName] = useState('')
  const [video, setVideo] = useState<Video | null>(null)
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [busy, setBusy] = useState(initialId ? '영상 조회' : '')
  const [error, setError] = useState('')
  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [showProgress, setShowProgress] = useState(false)
  const [progressError, setProgressError] = useState('')

  // 처리 후 영상 정보와 자막 갱신
  const refreshArtifacts = useCallback(async (videoId: string, signal?: AbortSignal) => {
    const response = await request(videoUrl(videoId), { signal })
    const result: Video = await response.json()
    if (!signal?.aborted) {
      setVideo(result)
      setTranscript(null)
    }
    const savedTranscript = await loadTranscript(result, signal)
    if (!signal?.aborted) setTranscript(savedTranscript)
  }, [])

  // 저장된 작업 복원 및 진행 중인 작업 추적 재개
  const restoreVideo = useCallback(async (videoId: string, signal?: AbortSignal) => {
    await refreshArtifacts(videoId, signal)
    const savedWorkflow = await loadWorkflow(videoId, signal)
    if (signal?.aborted) return
    setWorkflow(savedWorkflow)
    if (!savedWorkflow || workflowFinished(savedWorkflow)) return
    setProgressError('')
    setShowProgress(true)
    try {
      await followWorkflow(savedWorkflow, setWorkflow, signal)
    } catch (error) {
      if (!signal?.aborted) setProgressError(errorMessage(error))
    }
    if (!signal?.aborted) await refreshArtifacts(videoId, signal)
  }, [refreshArtifacts])

  // 새로고침 시 URL의 UUID로 영상 재조회
  useEffect(() => {
    if (!initialId) return
    const controller = new AbortController()
    void (async () => {
      try {
        await restoreVideo(initialId, controller.signal)
      } catch (error) {
        if (!controller.signal.aborted) setError(`영상 조회 실패 · ${errorMessage(error)}`)
      } finally {
        if (!controller.signal.aborted) setBusy('')
      }
    })()
    return () => controller.abort()
  }, [initialId, restoreVideo])

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

  // 선택한 영상 UUID를 조회 입력란과 URL에 저장
  function rememberVideo(videoId: string) {
    setLookupId(videoId)
    const url = new URL(window.location.href)
    url.searchParams.set('video', videoId)
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

  // MP4 업로드 후 반환된 UUID로 자동 편집 요청
  function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = new FormData(event.currentTarget)
    setWorkflow(null)
    setProgressError('')
    setShowProgress(true)
    void run('MP4 업로드', async () => {
      let uploaded: Video | undefined
      try {
        const response = await request(videosUrl, { method: 'POST', body })
        uploaded = await response.json() as Video
        setVideo(uploaded)
        setTranscript(null)
        rememberVideo(uploaded.video_id)
        const started = await request(`${videoUrl(uploaded.video_id)}/workflow`, { method: 'POST' })
        await followWorkflow(await started.json(), setWorkflow)
      } catch (error) {
        setProgressError(errorMessage(error))
      }
      if (uploaded) await refreshArtifacts(uploaded.video_id)
    })
  }

  // 입력한 UUID로 영상과 결과물 조회
  function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run('영상 조회', async () => {
      const videoId = lookupId.trim()
      await restoreVideo(videoId)
      rememberVideo(videoId)
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

  // 선택한 영상의 자막 수동 생성
  function transcribe(current: Video) {
    void run('자막 생성', async () => {
      const response = await request(`${videoUrl(current.video_id)}/transcribe`, { method: 'POST' })
      setTranscript(await response.json())
    })
  }

  // 원본·음성·프레임·자막 다운로드 경로 선택
  function download(current: Video, kind: keyof typeof downloads) {
    const { label, filename } = downloads[kind]
    downloadFile(`${videoUrl(current.video_id)}/download/${kind}`, label, filename)
  }

  // 결과물을 브라우저에 저장하고 임시 URL 해제
  function downloadFile(url: string, label: string, filename: string) {
    void run(`${label} 다운로드`, async () => {
      const response = await request(url)
      const objectUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = filename
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    })
  }

  // 완료 팝업을 닫은 현재 영상의 편집본 분석 ID
  const finishedAnalysis = !showProgress && workflow?.stage === 'completed'
    && workflow.video_id === video?.video_id ? workflow.analysis_id : null

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="container header-content">
          <span className="brand"><span className="brand-symbol"><Icon name="film" /></span> ShortsFlow <span>AI</span></span>
          <span className="connection" data-status={status} role="status">
            <span className="connection-dot" aria-hidden="true" />{statusLabels[status]}
          </span>
        </div>
      </header>
      <main className="container">
        {/* 서비스 소개와 MP4에서 편집본까지의 흐름 */}
        <section className="hero" aria-labelledby="page-title">
          <div>
            <p className="hero-label"><Icon name="spark" /> 자동 쇼츠 편집</p>
            <h1 id="page-title">긴 영상의 순간을<br /><span>쇼츠로.</span></h1>
            <p className="hero-description">MP4를 올리면 쇼츠 구간을 찾아 자막이 합성된 영상으로 편집합니다.</p>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="hero-orbit" />
            <div className="clip-card clip-card--source">
              <span className="clip-icon"><Icon name="film" /></span>
              <span>원본 영상</span>
              <div className="clip-timeline"><i /><i /><i /><i /><i /><i /></div>
            </div>
            <span className="clip-arrow"><Icon name="arrow" /></span>
            <div className="clip-card clip-card--output">
              <span className="clip-icon"><Icon name="play" /></span>
              <span>편집된 쇼츠</span>
              <div className="clip-timeline"><i /><i /><i /></div>
            </div>
          </div>
        </section>

        {busy && !showProgress && <p className="feedback" role="status">{busy} 중…</p>}
        {error && <p className="feedback feedback--error" role="alert"><Icon name="alert" />{error}</p>}
        {showProgress && <WorkflowDialog workflow={workflow} error={progressError} close={() => setShowProgress(false)} />}

        {/* MP4 업로드와 UUID 조회 영역 */}
        <div className="entry-grid">
          <section className="panel panel--upload" aria-labelledby="video-input">
            <div className="panel-heading">
              <span className="section-icon"><Icon name="upload" /></span>
              <h2 id="video-input">영상 업로드</h2>
            </div>
            <form onSubmit={upload}>
              <label className="file-picker" data-selected={!!fileName} htmlFor="video-file">
                <input id="video-file" name="file" type="file" accept=".mp4,video/mp4" required disabled={!!busy}
                  aria-label="MP4 파일 선택" aria-describedby="file-hint"
                  onChange={(event) => setFileName(event.target.files?.[0]?.name ?? '')} />
                <Icon className="file-picker-icon" name={fileName ? 'film' : 'upload'} />
                <span className="file-picker-copy">
                  <strong>{fileName || 'MP4 파일 선택'}</strong>
                  <small id="file-hint">MP4 · 최대 100 MiB</small>
                </span>
                <Icon className="file-picker-arrow" name="arrow" />
              </label>
              <button className="button button--primary upload-button" disabled={!!busy || !fileName}>
                <Icon name="spark" /> 업로드 및 자동 편집
              </button>
            </form>
          </section>
          <section className="panel panel--lookup" aria-labelledby="lookup-title">
            <div className="panel-heading">
              <span className="section-icon"><Icon name="search" /></span>
              <h2 id="lookup-title">기존 작업 조회</h2>
            </div>
            <p className="panel-description">영상 UUID로 이전 작업과 결과물을 다시 열 수 있습니다.</p>
            <form onSubmit={lookup}>
              <label className="field-label" htmlFor="video-id">영상 UUID</label>
              <input className="field" id="video-id" type="text" value={lookupId} required disabled={!!busy}
                placeholder="영상 UUID 입력" autoComplete="off" spellCheck={false}
                onChange={(event) => setLookupId(event.target.value)} />
              <button className="button lookup-button" disabled={!!busy}><Icon name="search" /> 조회</button>
            </form>
          </section>
        </div>

        {/* 영상 정보와 추출·다운로드 버튼 */}
        {video ? (
          <div className="job-grid" key={video.video_id}>
            <section className="panel panel--details" aria-labelledby="video-details">
              <div className="panel-heading">
                <span className="section-icon"><Icon name="film" /></span>
                <h2 id="video-details">영상 정보</h2>
              </div>
              <dl className="video-details">
                <dt>UUID</dt><dd>{video.video_id}</dd>
                <dt>파일 크기</dt><dd>{video.size_bytes.toLocaleString()} 바이트</dd>
                <dt>길이</dt><dd>{video.metadata.duration_seconds.toLocaleString()}초</dd>
                <dt>해상도</dt><dd>{video.metadata.width} × {video.metadata.height}</dd>
                <dt>프레임률</dt><dd>{video.metadata.fps.toLocaleString()} fps</dd>
                <dt>코덱</dt><dd>{video.metadata.video_codec}</dd>
                <dt>음성 트랙</dt><dd>{video.metadata.has_audio ? '있음' : '없음'}</dd>
              </dl>
            </section>
            {/* 원본·편집본 다운로드 및 수동 추출 버튼 */}
            <section className="panel" aria-labelledby="result-title">
              <div className="panel-heading">
                <span className="section-icon"><Icon name="download" /></span>
                <h2 id="result-title">결과물</h2>
              </div>
              <div className="controls result-downloads">
                {finishedAnalysis && (
                  <button className="button button--primary" type="button" disabled={!!busy} onClick={() => downloadFile(
                    `${videoUrl(video.video_id)}/download/shorts?analysis_id=${encodeURIComponent(finishedAnalysis)}`,
                    '편집 영상', 'shorts.mp4',
                  )}><Icon name="download" /> 편집 영상 다운로드</button>
                )}
                <button className="button" type="button" disabled={!!busy} onClick={() => download(video, 'source')}>
                  <Icon name="download" /> 원본 MP4 다운로드
                </button>
              </div>
              <div className="manual-section">
                <h3>음성 및 자막</h3>
                <div className="controls">
                  <button className="button" type="button" disabled={!!busy || !video.metadata.has_audio} onClick={() => extract(video, 'audio')}><Icon name="audio" /> 음성 추출</button>
                  <button className="button" type="button" disabled={!!busy || !video.audio_path} onClick={() => download(video, 'audio')}><Icon name="download" /> WAV 다운로드</button>
                  <button className="button" type="button" disabled={!!busy || !video.audio_path} onClick={() => transcribe(video)}><Icon name="text" /> 자막 생성</button>
                  <button className="button" type="button" disabled={!!busy || (!transcript && !video.transcript_path)} onClick={() => download(video, 'transcript')}><Icon name="download" /> 자막 JSON 다운로드</button>
                </div>
              </div>
              <form className="manual-section" onSubmit={(event) => {
                event.preventDefault()
                const seconds = String(new FormData(event.currentTarget).get('seconds'))
                extract(video, 'frame', seconds)
              }}>
                <label className="field-label" htmlFor="frame-seconds">프레임 추출 시점 (초)</label>
                <div className="controls">
                  <input className="field field--seconds" id="frame-seconds" name="seconds" type="number" min="0" step="any" defaultValue="0" required disabled={!!busy} />
                  <button className="button" disabled={!!busy}><Icon name="frame" /> 프레임 추출</button>
                  <button className="button" type="button" disabled={!!busy || !video.frame_path} onClick={() => download(video, 'frame')}><Icon name="download" /> JPG 다운로드</button>
                </div>
              </form>
            </section>
            {/* 자막 구간별 시작·종료 시각과 내용 표시 */}
            {transcript && (
              <section className="panel panel--transcript" aria-labelledby="transcript-title">
                <div className="panel-heading">
                  <span className="section-icon"><Icon name="text" /></span>
                  <h2 id="transcript-title">자막</h2>
                  <span className="transcript-language">감지 언어 {transcript.language}</span>
                </div>
                {transcript.segments.length > 0 ? (
                  <table className="transcript">
                    <thead>
                      <tr><th scope="col">시작 (초)</th><th scope="col">종료 (초)</th><th scope="col">대사</th></tr>
                    </thead>
                    <tbody>
                      {transcript.segments.map((segment, index) => (
                        <tr key={index}>
                          <td>{segmentTime.format(segment.start_seconds)}</td>
                          <td>{segmentTime.format(segment.end_seconds)}</td>
                          <td>{segment.text}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <p className="panel-description">감지된 대사가 없습니다.</p>}
              </section>
            )}
          </div>
        ) : (
          <section className="empty-results" aria-labelledby="empty-title">
            <span className="section-icon"><Icon name="download" /></span>
            <div><h2 id="empty-title">결과물</h2><p>영상을 업로드하거나 기존 작업을 조회하면 결과물이 여기에 표시됩니다.</p></div>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
