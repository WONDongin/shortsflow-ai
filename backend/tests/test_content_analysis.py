import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_engine
from app.main import app
from app.services import content_analysis


class ContentAnalysisTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(get_engine().dispose)

    def setUp(self):
        storage = TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.video_id = uuid4()
        self.path = Path(storage.name) / str(self.video_id)
        self.path.mkdir()
        self.analysis_env = Path(storage.name) / ".env"
        self.analysis_env.write_text("ANALYSIS_MOCK_MODE=false\n", encoding="utf-8")
        self.enterContext(patch.object(content_analysis, "ENV_FILE", self.analysis_env))
        self.write_metadata(60.0)
        self.segments = [
            {"start_seconds": 0.021995, "end_seconds": 10.021995, "text": "사랑이라는 말보다 먼저 나오는 말이 있어."},
            {"start_seconds": 10.021995, "end_seconds": 16.521995, "text": "하루 종일 보고 싶다는 말이야."},
            {"start_seconds": 16.521995, "end_seconds": 22.021995, "text": "해가 지는 순간에도 그래."},
        ]
        self.write_transcript(self.segments)
        self.enterContext(patch.dict(os.environ, {
            "VIDEO_STORAGE_DIR": storage.name, "OPENAI_API_KEY": "mock-key", "OPENAI_MODEL": "mock-model",
        }))
        self.addCleanup(self.delete_video)
        self.client = self.enterContext(TestClient(app))
        self.url = f"/api/videos/{self.video_id}"
        self.selection = {
            "start_segment_id": 1, "end_segment_id": 3,
            "title": "사랑한다는 말보다 먼저 나오는 말",
            "thumbnail_text": "하루 종일 보고 싶다",
            "reason": "첫 문장이 질문을 만들고 이어지는 대사가 답을 준다.",
        }

    def write_metadata(self, duration):
        self.path.joinpath("metadata.json").write_text(json.dumps({
            "video_id": str(self.video_id),
            "size_bytes": 1024,
            "metadata": {
                "duration_seconds": duration, "width": 720, "height": 1280,
                "fps": 24, "video_codec": "h264", "has_audio": True,
            },
        }), encoding="utf-8")

    def write_transcript(self, segments):
        self.path.joinpath("transcript.json").write_text(json.dumps({
            "video_id": str(self.video_id), "language": "ko", "segments": segments,
        }, ensure_ascii=False), encoding="utf-8")

    def delete_video(self):
        with get_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM shortsflow_app.videos WHERE id = :id"), {"id": self.video_id}
            )

    @staticmethod
    def model_response(candidate):
        return httpx.Response(200, json={"status": "completed", "output": [{
            "type": "message", "content": [
                {"type": "output_text", "text": json.dumps({"candidate": candidate})}
            ],
        }]})

    def request_and_read(self):
        request = self.client.post(f"{self.url}/analyze")
        self.assertEqual(request.status_code, 202, request.text)
        result = self.client.get(request.headers["Location"])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["analysis_id"], request.json()["analysis_id"])
        return result.json()

    def test_swagger_contract_and_original_boundaries(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("202", paths["/api/videos/{video_id}/analyze"]["post"]["responses"])
        source = self.client.get(f"{self.url}/transcript").json()["segments"]
        with patch.object(httpx, "post", return_value=self.model_response(self.selection)) as send:
            result = self.request_and_read()
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["candidate"], {
            **self.selection, "start_seconds": source[0]["start_seconds"],
            "end_seconds": source[2]["end_seconds"],
        })
        self.assertEqual(self.client.get(f"{self.url}/analysis").json(), result)
        body = send.call_args.kwargs["json"]
        self.assertEqual(body["model"], "mock-model")
        self.assertEqual(body["truncation"], "disabled")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(json.loads(body["input"])["segments"][0], {
            "segment_id": 1, "start": source[0]["start_seconds"],
            "end": source[0]["end_seconds"], "text": source[0]["text"],
        })

    def test_no_candidate_and_invalid_selections(self):
        cases = [
            (None, "no_candidate", None),
            ({**self.selection, "end_segment_id": 9}, "failed", "invalid_segment"),
            ({**self.selection, "start_segment_id": 3, "end_segment_id": 1}, "failed", "invalid_segment"),
            ({**self.selection, "end_segment_id": 1}, "failed", "invalid_segment"),
        ]
        for selection, status, code in cases:
            with self.subTest(selection=selection):
                with patch.object(httpx, "post", return_value=self.model_response(selection)):
                    result = self.request_and_read()
                self.assertEqual(result["status"], status, result)
                self.assertIsNone(result["candidate"])
                self.assertEqual(result["error"]["code"] if result["error"] else None, code)

    def test_local_mock_uses_saved_boundaries_and_skips_provider(self):
        self.write_transcript([*self.segments, *[
            {"start_seconds": start, "end_seconds": end, "text": words}
            for start, end, words in content_analysis.MOCK_SEGMENTS
        ]])
        for config in ("", "ANALYSIS_MOCK_MODE=true\n"):
            with self.subTest(config=config):
                self.analysis_env.write_text(config, encoding="utf-8")
                with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                    with patch.object(httpx, "post", side_effect=AssertionError("Unexpected provider call")) as send:
                        result = self.request_and_read()
                    send.assert_not_called()
                self.assertEqual(result["status"], "succeeded", result)
                candidate = result["candidate"]
                self.assertEqual((candidate["start_segment_id"], candidate["end_segment_id"]), (4, 5))
                self.assertEqual((candidate["start_seconds"], candidate["end_seconds"]), (22.021995, 41.521995))
                self.assertEqual(candidate["thumbnail_text"], "하루 종일 보고 싶다")

        params = {"analysis_id": result["analysis_id"]}
        self.assertEqual(self.client.get(f"{self.url}/shorts", params=params).status_code, 404)
        self.assertEqual(self.client.post(f"{self.url}/generate-shorts", params=params).status_code, 404)
        self.assertEqual(self.client.get(f"{self.url}/download/thumbnail").status_code, 422)

    def test_short_video_preserves_existing_segment_ids_and_checks_video_bounds(self):
        self.write_metadata(10.0)
        self.write_transcript([{**self.segments[0], "segment_id": 12, "end_seconds": 9.0}])
        selection = {**self.selection, "start_segment_id": 12, "end_segment_id": 12}
        with patch.object(httpx, "post", return_value=self.model_response(selection)):
            result = self.request_and_read()
            self.assertEqual(result["status"], "succeeded", result)
            self.assertEqual(result["candidate"]["end_seconds"], 9.0)
            self.write_transcript([{**self.segments[0], "segment_id": 12}])
            result = self.request_and_read()
            self.assertEqual(result["error"]["code"], "invalid_segment")

    def test_transcript_input_limit_and_provider_failures(self):
        with patch.object(httpx, "post") as send:
            self.path.joinpath("transcript.json").unlink()
            self.assertEqual(self.request_and_read()["error"]["code"], "transcript_not_ready")
            self.write_transcript([])
            self.assertEqual(self.request_and_read()["status"], "no_candidate")
            self.write_transcript([{**self.segments[0], "text": "가" * 34_000}])
            self.assertEqual(self.request_and_read()["error"]["code"], "input_too_long")
            send.assert_not_called()

        self.write_transcript(self.segments)
        for code, provider_error, status in [
            ("input_too_long", "context_length_exceeded", 400),
            ("api_error", "invalid_api_key", 401),
        ]:
            response = httpx.Response(status, json={"error": {"code": provider_error}})
            with patch.object(httpx, "post", return_value=response):
                self.assertEqual(self.request_and_read()["error"]["code"], code)

    def test_concurrent_requests_share_active_analysis(self):
        started = Event()
        release = Event()

        def respond(*args, **kwargs):
            started.set()
            if not release.wait(10):
                raise RuntimeError("Timed out waiting on the duplicate analysis request.")
            return self.model_response(self.selection)

        with patch.object(content_analysis.httpx, "post", side_effect=respond) as send:
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(self.client.post, f"{self.url}/analyze")
                try:
                    self.assertTrue(started.wait(10))
                    duplicate = self.client.post(f"{self.url}/analyze")
                    self.assertEqual(duplicate.status_code, 202, duplicate.text)
                    self.assertEqual(duplicate.json()["status"], "running")
                finally:
                    release.set()
                self.assertEqual(first.result().json()["analysis_id"], duplicate.json()["analysis_id"])
            send.assert_called_once()
        self.assertEqual(self.client.get(duplicate.headers["Location"]).json()["status"], "succeeded")
