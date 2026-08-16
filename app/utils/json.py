"""Extract and parse JSON from LLM responses, including fenced markdown."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class JSONParseError(ValueError):
    """Raised when LLM output cannot be parsed as a JSON object."""


def parse_llm_json(text: str | None) -> dict[str, Any]:
    if text is None or not str(text).strip():
        raise JSONParseError("LLM returned an empty response")

    raw = str(text).strip()
    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()

    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise JSONParseError("LLM response did not contain a JSON object")
        raw = raw[start : end + 1]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"Invalid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise JSONParseError("LLM JSON root must be an object")
    return parsed
