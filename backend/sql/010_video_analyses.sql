-- 영상별 분석 상태·후보·오류를 저장하는 테이블 생성
CREATE TABLE IF NOT EXISTS shortsflow_app.video_analyses (
    id uuid PRIMARY KEY,
    video_id uuid NOT NULL REFERENCES shortsflow_app.videos(id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'no_candidate', 'failed')),
    candidate jsonb,
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((status = 'succeeded') = (candidate IS NOT NULL)),
    CHECK ((status = 'failed') = (error IS NOT NULL))
);

-- 영상마다 대기·실행 중인 분석을 하나로 제한
CREATE UNIQUE INDEX IF NOT EXISTS video_analyses_active_idx
    ON shortsflow_app.video_analyses (video_id)
    WHERE status IN ('queued', 'running');

-- 영상별 최신 분석 조회 인덱스
CREATE INDEX IF NOT EXISTS video_analyses_latest_idx
    ON shortsflow_app.video_analyses (video_id, created_at DESC, id DESC);
