import unittest

from app.services.media_preview import MediaPreviewer


class MediaPreviewTests(unittest.TestCase):
    def test_video_quality_preview_prefers_mp4_and_combines_audio_size(self):
        previewer = MediaPreviewer()
        qualities = previewer._video_qualities(
            [
                {
                    "height": 720,
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "none",
                    "tbr": 4000,
                    "filesize": 4_000_000,
                },
                {
                    "height": 720,
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "none",
                    "tbr": 2500,
                    "filesize": 2_500_000,
                },
                {
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a",
                    "abr": 128,
                    "filesize": 500_000,
                },
            ]
        )

        self.assertEqual([q.quality for q in qualities], ["best", "720p"])
        self.assertEqual(qualities[1].ext, "mp4")
        self.assertEqual(qualities[1].filesize_bytes, 3_000_000)


if __name__ == "__main__":
    unittest.main()
