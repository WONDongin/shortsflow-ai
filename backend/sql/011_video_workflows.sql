-- 영상별 n8n 진행 단계·분석 ID·실패 원인을 저장하는 테이블 생성
CREATE TABLE IF NOT EXISTS shortsflow_app.video_workflows (
    video_id uuid PRIMARY KEY REFERENCES shortsflow_app.videos(id) ON DELETE CASCADE,
    callback_token uuid NOT NULL,
    stage text NOT NULL CHECK (stage IN (
        'queued', 'extracting', 'transcribing', 'analyzing',
        'rendering', 'completed', 'no_candidate', 'failed'
    )),
    analysis_id uuid,
    error text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
