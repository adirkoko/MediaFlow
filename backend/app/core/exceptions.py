class QuotaExceeded(Exception):
    pass


class AllPlaylistItemsFailed(Exception):
    def __init__(self, message: str, total: int, failed: int):
        super().__init__(message)
        self.total = total
        self.failed = failed
