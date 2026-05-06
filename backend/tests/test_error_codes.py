import unittest

from app.core.exceptions import AllPlaylistItemsFailed, JobCanceled
from app.services.error_codes import classify_error, is_retryable_error


class ErrorCodeTests(unittest.TestCase):
    def test_permanent_errors_are_not_retried(self):
        permanent_examples = [
            RuntimeError("Requested format is not available"),
            RuntimeError("Unsupported URL"),
            RuntimeError("Private video"),
            RuntimeError("Video unavailable"),
            RuntimeError("Sign in to confirm your age"),
            RuntimeError("Cookies are required"),
            AllPlaylistItemsFailed("All playlist items failed", total=3, failed=3),
            ValueError("Unsupported quality. Supported video qualities: best"),
        ]

        for exc in permanent_examples:
            with self.subTest(error=str(exc)):
                self.assertFalse(is_retryable_error(exc))

    def test_network_errors_are_retryable(self):
        self.assertEqual(classify_error(RuntimeError("temporary failure")), "NETWORK")
        self.assertTrue(is_retryable_error(RuntimeError("temporary failure")))

    def test_canceled_is_not_retryable(self):
        self.assertFalse(is_retryable_error(JobCanceled("Job canceled by user")))


if __name__ == "__main__":
    unittest.main()
