import tempfile
import unittest
from pathlib import Path

from app.services.youtube_processor import YouTubeProcessor


class YouTubeProcessorFilenameTests(unittest.TestCase):
    def test_renames_output_to_artist_and_track(self):
        processor = YouTubeProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "abc123.mp3"
            path.write_bytes(b"fake audio")

            renamed = processor._rename_media_output(
                path,
                {"artist": "Test Artist", "track": "Test Song", "title": "abc123"},
            )

            self.assertEqual(renamed.name, "Test Artist - Test Song.mp3")
            self.assertTrue(renamed.exists())
            self.assertFalse(path.exists())

    def test_playlist_rename_preserves_prefix(self):
        processor = YouTubeProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "001-abc123.mp3"
            path.write_bytes(b"fake audio")

            renamed = processor._rename_media_output(
                path,
                {"uploader": "Uploader", "title": "Readable Title"},
                prefix="001-",
            )

            self.assertEqual(renamed.name, "001-Uploader - Readable Title.mp3")

    def test_remote_components_true_enables_github_ejs(self):
        processor = YouTubeProcessor()
        from app.services import youtube_processor

        original = youtube_processor.settings.ytdlp_remote_components
        try:
            youtube_processor.settings.ytdlp_remote_components = "true"
            self.assertEqual(processor._remote_components(), ["ejs:github"])
        finally:
            youtube_processor.settings.ytdlp_remote_components = original


if __name__ == "__main__":
    unittest.main()
