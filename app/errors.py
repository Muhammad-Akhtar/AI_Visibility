"""Consistent JSON error responses for every endpoint."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    """Application-level API error with a stable JSON body."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def format_pydantic_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else "Invalid request"


def _wants_json() -> bool:
    path = request.path or ""
    return path.startswith("/api/") or path == "/health"


def _respond(code: str, message: str, status: int):
    if _wants_json():
        return jsonify(_error_body(code, message)), status
    template = "errors/500.html" if status >= 500 else "errors/404.html"
    return (
        render_template(
            template,
            nav="",
            profile=None,
            code=code,
            message=message,
            status=status,
        ),
        status,
    )


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify(_error_body(err.code, err.message)), err.status

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return jsonify(_error_body("validation_error", format_pydantic_error(err))), 400

    @app.errorhandler(404)
    def handle_not_found(err):
        message = getattr(err, "description", None) or "Resource not found"
        return _respond("not_found", message, 404)

    @app.errorhandler(405)
    def handle_method_not_allowed(err):
        return _respond("method_not_allowed", "Method not allowed", 405)

    @app.errorhandler(429)
    def handle_rate_limited(err):
        message = getattr(err, "description", None) or "Rate limit exceeded"
        return _respond("rate_limited", str(message), 429)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        code = (err.name or "http_error").lower().replace(" ", "_")
        status = err.code or 500
        message = err.description or err.name or "Request failed"
        return _respond(code, message, status)

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        app.logger.exception("unhandled_exception")
        return _respond("internal_error", "An unexpected error occurred", 500)
