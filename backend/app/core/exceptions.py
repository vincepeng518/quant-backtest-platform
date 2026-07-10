from __future__ import annotations

from typing import Any


class AppException(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class NotFound(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__("NOT_FOUND", detail, 404)


class ValidationError(AppException):
    def __init__(self, detail: str):
        super().__init__("VALIDATION_ERROR", detail, 400)


class TaskNotReady(AppException):
    def __init__(self, task_id: str):
        super().__init__("TASK_NOT_READY", f"Task {task_id} is not complete", 400)