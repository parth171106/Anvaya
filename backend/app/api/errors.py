from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict | None = None):
        self.status, self.code, self.message, self.detail = status, code, message, detail or {}


def envelope(status: int, code: str, message: str, detail=None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "detail": detail or {}}}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return envelope(e.status, e.code, e.message, e.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        return envelope(422, "validation_error", "Request validation failed", {"errors": e.errors()})

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException):
        code = {404: "not_found", 405: "bad_request"}.get(e.status_code, "bad_request")
        return envelope(e.status_code, code, str(e.detail))


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")
