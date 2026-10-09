from enum import StrEnum


class ErrorCode(StrEnum):
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_FILE = "EMPTY_FILE"
    NO_TEXT = "NO_TEXT"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    CORRUPT_FILE = "CORRUPT_FILE"
    INTERRUPTED = "INTERRUPTED"
    AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
    INTERNAL = "INTERNAL"


class DocumentError(Exception):
    """A failure with a stable machine-readable code and a message safe to show to the user."""

    def __init__(self, code: ErrorCode, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
