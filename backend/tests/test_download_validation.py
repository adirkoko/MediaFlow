import unittest

from app.services.download_validation import validate_download_request


class DownloadValidationTests(unittest.TestCase):
    def test_audio_accepts_only_best_quality(self):
        opts = validate_download_request(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="audio",
            quality="BEST",
        )

        self.assertEqual(opts.mode, "audio")
        self.assertEqual(opts.quality, "best")
        self.assertIsNone(opts.height)

        with self.assertRaisesRegex(ValueError, "Audio mode supports only"):
            validate_download_request(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mode="audio",
                quality="720p",
            )

    def test_video_quality_is_canonical_and_allowlisted(self):
        opts = validate_download_request(
            url="https://youtu.be/dQw4w9WgXcQ",
            mode="video",
            quality="720",
        )

        self.assertEqual(opts.quality, "720p")
        self.assertEqual(opts.height, 720)

        with self.assertRaisesRegex(ValueError, "Unsupported quality"):
            validate_download_request(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mode="video",
                quality="999p",
            )

    def test_rejects_non_youtube_urls(self):
        with self.assertRaisesRegex(ValueError, "Only YouTube URLs"):
            validate_download_request(
                url="https://example.com/watch?v=dQw4w9WgXcQ",
                mode="video",
                quality="best",
            )

    def test_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "Unsupported mode"):
            validate_download_request(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                mode="gif",
                quality="best",
            )


if __name__ == "__main__":
    unittest.main()
