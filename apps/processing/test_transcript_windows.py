from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from .services import groq_provider


class TranscriptWindowTests(SimpleTestCase):
    @patch("apps.processing.services.groq_provider.time.sleep")
    @patch("apps.processing.services.groq_provider.requests.post")
    def test_window_requests_respect_short_provider_token_cooldowns(self, post, sleep):
        from unittest.mock import Mock
        rate_limited = Mock(status_code=429, headers={"retry-after": "35"})
        ok = Mock(status_code=200)
        post.side_effect = [rate_limited, ok]
        self.assertIs(groq_provider._post_with_rate_limit_retries("https://example.test", endpoint="chat/completions", model="test"), ok)
        sleep.assert_called_once_with(35)

    @patch("apps.processing.services.groq_provider.time.sleep")
    @patch("apps.processing.services.groq_provider.requests.post")
    def test_oversized_request_is_not_retried_unchanged(self, post, sleep):
        from unittest.mock import Mock
        response = Mock(status_code=413, headers={})
        response.json.return_value = {"error": {"code": "rate_limit_exceeded", "message": "Request too large for model"}}
        post.return_value = response
        self.assertIs(groq_provider._post_with_rate_limit_retries("https://example.test", endpoint="chat/completions", model="test"), response)
        post.assert_called_once()
        sleep.assert_not_called()

    def test_all_segments_are_preserved_with_bounded_overlap(self):
        lines = [f"[{index * 1000}-{(index + 1) * 1000}] Segment {index}: " + "word " * 30 + "\n" for index in range(80)]
        windows = groq_provider._transcript_windows("".join(lines), 1200)
        self.assertGreater(len(windows), 1)
        self.assertTrue(all(len(window) <= 1200 for window in windows))
        for line in lines:
            self.assertTrue(any(line in window for window in windows))
        self.assertTrue(any(line in windows[0] and line in windows[1] for line in lines))

    def test_very_long_segment_remains_bounded_and_keeps_timestamp(self):
        windows = groq_provider._transcript_windows("[0-60000] " + "a" * 5000, 1000)
        self.assertTrue(all(len(window) <= 1000 for window in windows))
        self.assertTrue(all(window.startswith("[0-60000]") for window in windows))
        self.assertEqual(sum(window.count("a") for window in windows), 5000)

    @override_settings(GROQ_TRANSCRIPT_WINDOW_CHARS=100)
    @patch("apps.processing.services.groq_provider._plan_package_window")
    def test_candidates_from_end_of_recording_are_ranked_and_overlap_deduplicated(self, plan):
        plan.side_effect = [
            {"summary": "First", "clips": [{"title": "Early", "start_ms": 0, "end_ms": 10000, "score": 7}]},
            {"summary": "Second", "clips": [{"title": "Late", "start_ms": 20000, "end_ms": 30000, "score": 9}, {"title": "Overlap", "start_ms": 22000, "end_ms": 29000, "score": 8}]},
        ]
        result = groq_provider.plan_package("[0-10000] " + "a" * 65 + "\n[20000-30000] " + "b" * 65, "Context", 60000, {"desired_clip_count": 2})
        self.assertEqual([clip["title"] for clip in result["clips"]], ["Late", "Early"])
        self.assertEqual([clip["rank"] for clip in result["clips"]], [1, 2])
        self.assertEqual(plan.call_count, 2)
