import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
import yt_dlp

from .services import youtube
from .services.public_media import PublicMediaError
from .services.run_control import PipelineCancelled


URL = "https://www.youtube.com/watch?v=BaW_jenozKc"


@override_settings(YOUTUBE_IMPORTS_ENABLED=False, YOUTUBE_PROXY_URL="", YOUTUBE_IP_FAMILY="auto")
class YouTubeImportTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        settings_override = override_settings(MEDIA_ROOT=self.work)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def test_urls_are_canonical_and_playlists_or_untrusted_hosts_are_rejected(self):
        self.assertEqual(youtube.canonical_url("https://youtu.be/BaW_jenozKc?t=10"), URL)
        for url in (URL + "&list=abc", "https://youtube.com.attacker.test/watch?v=BaW_jenozKc",
                    "http://localhost/video", "https://youtube.com/playlist?list=x"):
            with self.assertRaises(PublicMediaError):
                youtube.canonical_url(url)

    @patch.object(youtube.yt_dlp, "YoutubeDL")
    def test_default_test_reads_metadata_without_media_or_credentials(self, factory):
        factory.return_value.__enter__.return_value.extract_info.return_value = {
            "id": "BaW_jenozKc", "title": "Test video", "duration": 10,
            "url": "https://signed-media.example/private-token",
        }
        result = youtube.import_video(URL, self.work)
        self.assertEqual(result["title"], "Test video")
        self.assertNotIn("url", result)
        options = factory.call_args.args[0]
        self.assertTrue(options["simulate"])
        self.assertNotIn("cookiefile", options)
        self.assertNotIn("cookiesfrombrowser", options)
        self.assertEqual(options["sleep_interval_requests"], 1.5)
        self.assertEqual(options["retries"], 0)
        factory.return_value.__enter__.return_value.extract_info.assert_called_once_with(URL, download=False)
        self.assertFalse(list(self.work.glob("youtube-*")))

    @patch.object(youtube.yt_dlp, "YoutubeDL")
    def test_live_is_disabled_before_network_access(self, factory):
        with self.assertRaises(PublicMediaError):
            youtube.import_video(URL, self.work, simulate=False)
        factory.assert_not_called()

    @patch.object(youtube.yt_dlp, "YoutubeDL")
    @override_settings(YOUTUBE_IMPORTS_ENABLED=True)
    def test_live_returns_completed_media_and_removes_temporary_files(self, factory):
        def extract(url, download):
            self.assertTrue(download)
            options = factory.call_args.args[0]
            Path(options["outtmpl"].replace("%(ext)s", "mkv")).write_bytes(b"media")
            return {"id": "BaW_jenozKc"}
        factory.return_value.__enter__.return_value.extract_info.side_effect = extract
        result = youtube.import_video(URL, self.work, simulate=False)
        self.assertEqual(result.read_bytes(), b"media")
        self.assertEqual(list(self.work.glob("youtube-*")), [result])

    @patch.object(youtube.yt_dlp, "YoutubeDL")
    def test_block_sets_persistent_cooldown_and_redacts_diagnostics(self, factory):
        factory.return_value.__enter__.return_value.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "HTTP Error 429 proxy=http://user:secret@host"
        )
        with self.assertRaises(PublicMediaError) as error:
            youtube.import_video(URL, self.work)
        self.assertNotIn("secret", str(error.exception))
        with self.assertRaisesMessage(PublicMediaError, "cooling down"):
            youtube.import_video(URL, self.work)
        self.assertEqual(factory.return_value.__enter__.return_value.extract_info.call_count, 1)

    def test_parallel_imports_cannot_acquire_same_slot(self):
        with youtube._request_slot():
            with self.assertRaisesMessage(PublicMediaError, "Another YouTube import"):
                with youtube._request_slot():
                    self.fail("Acquired duplicate slot")

    @override_settings(PUBLIC_MEDIA_MAX_BYTES=5)
    def test_progress_enforces_combined_stream_size_and_cancellation(self):
        options = youtube._options(self.work, simulate=False)
        progress = options["progress_hooks"][0]
        progress({"filename": "video", "downloaded_bytes": 4})
        with self.assertRaises(PublicMediaError):
            progress({"filename": "audio", "downloaded_bytes": 4})
        def cancel():
            raise PipelineCancelled("Stopped")
        options = youtube._options(self.work, simulate=False, check_active=cancel)
        with self.assertRaises(PipelineCancelled):
            options["progress_hooks"][0]({})

    def test_live_and_upcoming_are_rejected(self):
        options = youtube._options(self.work, simulate=True)
        with self.assertRaises(PublicMediaError):
            options["match_filter"]({"is_live": True})

    @override_settings(YOUTUBE_COOKIE_FILE="", YOUTUBE_COOKIES_BROWSER="chrome")
    def test_browser_credentials_require_explicit_opt_in(self):
        self.assertNotIn("cookiesfrombrowser", youtube._options(self.work, simulate=True))
        self.assertEqual(youtube._options(self.work, simulate=True, use_auth=True)["cookiesfrombrowser"], ("chrome", None))

    def test_command_requires_rights_and_output_for_downloads(self):
        with self.assertRaises(CommandError):
            call_command("check_youtube_import", URL, stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command("check_youtube_import", URL, rights_confirmed=True, download=True, stdout=io.StringIO())

    @patch("apps.processing.management.commands.check_youtube_import.import_video")
    def test_command_defaults_to_metadata_only(self, importer):
        importer.return_value = {"id": "test"}
        output = io.StringIO()
        call_command("check_youtube_import", URL, rights_confirmed=True, stdout=output)
        self.assertTrue(importer.call_args.kwargs["simulate"])
        self.assertFalse(importer.call_args.kwargs["use_auth"])
        self.assertIn('"id": "test"', output.getvalue())

    def test_options_construct_real_downloader_without_network(self):
        with yt_dlp.YoutubeDL(youtube._options(self.work, simulate=True)) as downloader:
            self.assertTrue(downloader.params["simulate"])

    def test_cookie_copy_is_temporary_and_original_is_not_modified(self):
        original = self.work / "original.cookies.txt"
        original.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        with override_settings(YOUTUBE_COOKIE_FILE=str(original), YOUTUBE_COOKIES_BROWSER=""):
            with TemporaryDirectory(dir=self.work) as temporary:
                options = youtube._options(temporary, simulate=True, use_auth=True)
                copy = Path(options["cookiefile"])
                self.assertNotEqual(copy, original)
                copy.write_text("changed", encoding="utf-8")
            self.assertFalse(copy.exists())
            self.assertEqual(original.read_text(), "# Netscape HTTP Cookie File\n")

    @patch.object(youtube.yt_dlp, "YoutubeDL")
    @override_settings(YOUTUBE_IMPORTS_ENABLED=True, PUBLIC_MEDIA_MAX_BYTES=4)
    def test_oversized_completed_download_is_removed(self, factory):
        def extract(url, download):
            options = factory.call_args.args[0]
            Path(options["outtmpl"].replace("%(ext)s", "mkv")).write_bytes(b"oversized")
            return {"id": "BaW_jenozKc"}
        factory.return_value.__enter__.return_value.extract_info.side_effect = extract
        with self.assertRaisesMessage(PublicMediaError, "size limit"):
            youtube.import_video(URL, self.work, simulate=False)
        self.assertFalse(list(self.work.glob("youtube-*")))
