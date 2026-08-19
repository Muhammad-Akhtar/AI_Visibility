"""Formatted stdout + per-run file tracing for internal and third-party API calls."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

_SEPARATOR = "=" * 80
_SUB_SEPARATOR = "-" * 80
_STDOUT_MAX_CHARS = 8000

# Project root / pipeline_logs/
_LOG_DIR = Path(__file__).resolve().parents[2] / "pipeline_logs"
_session = threading.local()


class _PipelineLogSession:
    def __init__(
        self,
        *,
        mode: str,
        run_id: str,
        log_path: Path,
        profile_uuid: str | None = None,
        query_uuid: str | None = None,
    ) -> None:
        self.mode = mode
        self.run_id = run_id
        self.profile_uuid = profile_uuid
        self.query_uuid = query_uuid
        self.log_path = log_path
        self.order = 0
        self._file: TextIO = log_path.open("w", encoding="utf-8")
        self._write_header()

    def _write_header(self) -> None:
        started = datetime.now(timezone.utc).isoformat()
        lines = [
            _SEPARATOR,
            "PIPELINE API TRACE LOG",
            _SEPARATOR,
            f"Mode:         {self.mode}",
            f"Run ID:       {self.run_id}",
        ]
        if self.profile_uuid:
            lines.append(f"Profile UUID: {self.profile_uuid}")
        if self.query_uuid:
            lines.append(f"Query UUID:   {self.query_uuid}")
        lines.extend(
            [
                f"Started (UTC): {started}",
                f"Log file:      {self.log_path}",
                _SEPARATOR,
                "",
            ]
        )
        self._file.write("\n".join(lines))
        self._file.flush()

    def next_order(self) -> int:
        self.order += 1
        return self.order

    def write(self, text: str) -> None:
        self._file.write(text)
        if not text.endswith("\n"):
            self._file.write("\n")
        self._file.flush()

    def close(self) -> None:
        self._file.write(
            f"\n{_SEPARATOR}\nLOG ENDED (UTC): {datetime.now(timezone.utc).isoformat()}\n{_SEPARATOR}\n"
        )
        self._file.flush()
        self._file.close()


def _active_session() -> _PipelineLogSession | None:
    return getattr(_session, "current", None)


def is_pipeline_log_active() -> bool:
    return _active_session() is not None


def get_pipeline_log_path() -> Path | None:
    session = _active_session()
    return session.log_path if session else None


def start_pipeline_log(
    *,
    mode: str,
    run_id: str,
    profile_uuid: str | None = None,
    query_uuid: str | None = None,
) -> Path:
    """Open a new per-run trace log. One active session per thread."""
    if _active_session() is not None:
        end_pipeline_log()

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in run_id)[:64]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"pipeline_{mode}_{safe_id}_{timestamp}.txt"
    log_path = _LOG_DIR / filename

    _session.current = _PipelineLogSession(
        mode=mode,
        run_id=run_id,
        log_path=log_path,
        profile_uuid=profile_uuid,
        query_uuid=query_uuid,
    )
    return log_path


def register_pipeline_run_id(run_uuid: str) -> None:
    """Attach the DB run UUID to an already-open log session."""
    session = _active_session()
    if session is None:
        return
    session.run_id = run_uuid
    session.write(f"[META] Pipeline run UUID registered: {run_uuid}")


def end_pipeline_log() -> Path | None:
    """Close the active trace log file."""
    session = _active_session()
    if session is None:
        return None
    path = session.log_path
    session.close()
    delattr(_session, "current")
    print(f"[PIPELINE LOG] Saved trace to {path}", flush=True)
    return path


def _format_body(value: Any, *, truncate: bool) -> str:
    if value is None:
        return "(none)"
    try:
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if truncate and len(text) > _STDOUT_MAX_CHARS:
        omitted = len(text) - _STDOUT_MAX_CHARS
        return f"{text[:_STDOUT_MAX_CHARS]}\n... [truncated, {omitted} chars omitted]"
    return text


def _indent_block(body: str) -> str:
    return "\n".join(f"  {line}" if line else "  " for line in body.splitlines())


def _emit(*, stdout_text: str, file_text: str | None = None) -> None:
    print(stdout_text, flush=True)
    session = _active_session()
    if session is None:
        return
    session.write(file_text if file_text is not None else stdout_text)


def _order_prefix() -> str:
    session = _active_session()
    if session is None:
        return ""
    order = session.next_order()
    return f"[{order:03d}] "


def print_api_request(
    *,
    provider: str,
    operation: str,
    method: str,
    url: str,
    payload: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    prefix = _order_prefix()
    header = (
        f"\n{_SEPARATOR}\n"
        f"{prefix}[API REQUEST] {provider} :: {operation}\n"
        f"{_SUB_SEPARATOR}\n"
        f"  Method: {method}\n"
        f"  URL:    {url}\n"
    )
    meta = ""
    if extra:
        meta = "  Meta:\n" + "".join(f"    {key}: {value}\n" for key, value in extra.items())
    stdout_payload = _indent_block(_format_body(payload, truncate=True))
    file_payload = _indent_block(_format_body(payload, truncate=False))
    stdout_text = f"{header}{meta}  Payload:\n{stdout_payload}\n{_SEPARATOR}"
    file_text = f"{header}{meta}  Payload:\n{file_payload}\n{_SEPARATOR}"
    _emit(stdout_text=stdout_text, file_text=file_text)


def print_api_response(
    *,
    provider: str,
    operation: str,
    url: str,
    response: Any = None,
    status: str | int | None = None,
    error: str | None = None,
) -> None:
    prefix = _order_prefix()
    header = (
        f"\n{_SEPARATOR}\n"
        f"{prefix}[API RESPONSE] {provider} :: {operation}\n"
        f"{_SUB_SEPARATOR}\n"
        f"  URL:    {url}\n"
    )
    if status is not None:
        header += f"  Status: {status}\n"
    if error:
        header += f"  Error:  {error}\n"
    stdout_body = _indent_block(_format_body(response, truncate=True))
    file_body = _indent_block(_format_body(response, truncate=False))
    stdout_text = f"{header}  Response:\n{stdout_body}\n{_SEPARATOR}"
    file_text = f"{header}  Response:\n{file_body}\n{_SEPARATOR}"
    _emit(stdout_text=stdout_text, file_text=file_text)


def print_pipeline_step(
    *,
    step: str,
    detail: str | None = None,
    payload: Any = None,
    response: Any = None,
) -> None:
    prefix = _order_prefix()
    header = f"\n{_SEPARATOR}\n{prefix}[PIPELINE] {step}\n"
    if detail:
        header += f"  {detail}\n"
    stdout_parts = [header]
    file_parts = [header]
    if payload is not None:
        stdout_parts.append("  Input:\n" + _indent_block(_format_body(payload, truncate=True)))
        file_parts.append("  Input:\n" + _indent_block(_format_body(payload, truncate=False)))
    if response is not None:
        stdout_parts.append("  Output:\n" + _indent_block(_format_body(response, truncate=True)))
        file_parts.append("  Output:\n" + _indent_block(_format_body(response, truncate=False)))
    stdout_parts.append(_SEPARATOR)
    file_parts.append(_SEPARATOR)
    _emit(stdout_text="\n".join(stdout_parts), file_text="\n".join(file_parts))
