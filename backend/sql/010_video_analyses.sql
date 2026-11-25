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

CREATE UNIQUE INDEX IF NOT EXISTS video_analyses_active_idx
    ON shortsflow_app.video_analyses (video_id)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS video_analyses_latest_idx
    ON shortsflow_app.video_analyses (video_id, created_at DESC, id DESC);
