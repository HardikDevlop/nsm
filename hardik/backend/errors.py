from dataclasses import dataclass
from typing import Any

@dataclass
class NMSException(Exception):
    code: str
    message: str
    status_code: int = 400
    detail: str | None = None
    suggestion: str | None = None
    retryable: bool = False


def error_payload(exc: NMSException, request_id: str | None = None) -> dict[str, Any]:
    return {k: v for k, v in {
        "code": exc.code, "message": exc.message, "detail": exc.detail,
        "suggestion": exc.suggestion, "retryable": exc.retryable,
        "request_id": request_id,
    }.items() if v is not None}
