from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.schemas.video import TranscriptSegment
from app.services.shorts import subtitle_filters


class ShortsSubtitleTests(TestCase):
    def test_selected_segments_use_clip_relative_times_and_literal_text(self):
        segments = [
            TranscriptSegment(start_seconds=16.521995, end_seconds=22.021995, text="이전 자막"),
            TranscriptSegment(start_seconds=22.021995, end_seconds=36.021995, text="그냥 네가 보고 싶다"),
            TranscriptSegment(start_seconds=36.021995, end_seconds=41.521995, text="참 많이 보고 싶다"),
            TranscriptSegment(start_seconds=41.521995, end_seconds=46.521995, text="다음 자막"),
        ]
        with TemporaryDirectory() as folder:
            staging = Path(folder)
            filters = subtitle_filters(staging, segments, 22.021995, 41.521995)
            self.assertEqual(len(filters), 2)
            self.assertTrue(filters[0].endswith(":enable='gte(t,0.000000)*lt(t,14.000000)'"))
            self.assertTrue(filters[1].endswith(":enable='gte(t,14.000000)*lt(t,19.500000)'"))
            self.assertEqual((staging / "subtitle-0.txt").read_text(encoding="utf-8"), "그냥 네가 보고 싶다")
            self.assertEqual((staging / "subtitle-1.txt").read_text(encoding="utf-8"), "참 많이 보고 싶다")

    def test_cues_are_clipped_and_overlaps_do_not_draw_two_captions(self):
        segments = [
            TranscriptSegment(start_seconds=1, end_seconds=4, text="first"),
            TranscriptSegment(start_seconds=3, end_seconds=9, text="second"),
        ]
        with TemporaryDirectory() as folder:
            filters = subtitle_filters(Path(folder), segments, 2, 5)
        self.assertEqual(len(filters), 2)
        self.assertTrue(filters[0].endswith(":enable='gte(t,0)*lt(t,1.0)'"))
        self.assertTrue(filters[1].endswith(":enable='gte(t,1.0)*lt(t,3)'"))
