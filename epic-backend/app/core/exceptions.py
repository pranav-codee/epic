"""Domain exceptions + a global handler that translates them to clean HTTP responses."""
from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidStateTransition(DomainError):
    status_code = 409


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class StorageQuotaExceeded(DomainError):
    """Resource Exhaustion (CWE-770): raised when an attachment upload would exceed the
    per-ticket count/size cap or the per-user total storage cap."""
    status_code = 413


async def domain_error_handler(_request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.__class__.__name__, "detail": exc.message})