"""Structured logging with a per-pipeline-run correlation field."""

from __future__ import annotations

import logging


class RunUuidDefaultFilter(logging.Filter):
    """Ensure every record has `run_uuid` so the log format never KeyErrors."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_uuid"):
            record.run_uuid = "-"
        return True


def configure_logging(level: int = logging.INFO) -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(run_uuid)s] %(name)s: %(message)s"
    )
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(RunUuidDefaultFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.addFilter(RunUuidDefaultFilter())
            handler.setFormatter(formatter)
    root.setLevel(level)
    logging.getLogger("app").addFilter(RunUuidDefaultFilter())
