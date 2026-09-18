"""Domain/application errors mapped to HTTP responses."""

from __future__ import annotations


class AppError(Exception):
    """Base application error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=404)


class ValidationAppError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=400)


class ConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)
