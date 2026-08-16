"""Opportunity score: demand × ease × visibility gap × commercial intent."""

from __future__ import annotations

import math

VOLUME_CAP = 10_000

INTENT_WEIGHTS: dict[str, float] = {
    "transactional": 1.00,
    "commercial": 0.85,
    "informational": 0.45,
    "navigational": 0.15,
}

WEIGHT_VOLUME = 0.35
WEIGHT_EASE = 0.25
WEIGHT_GAP = 0.25
WEIGHT_INTENT = 0.15


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def volume_norm(search_volume: int | float | None) -> float:
    volume = max(0.0, float(search_volume or 0))
    return _clip(math.log10(1.0 + volume) / math.log10(1.0 + VOLUME_CAP))


def ease_score(competitive_difficulty: int | float | None) -> float:
    difficulty = _clip(float(competitive_difficulty or 0) / 100.0)
    return 1.0 - difficulty


def visibility_gap(
    domain_visible: bool | None,
    visibility_position: int | None,
) -> float:
    """How much ranking gap remains for the target domain.

    Not appearing at all is the maximum opportunity. Position 1 is none.
    Unknown visibility (failed SERP) uses a conservative 0.7 so we do not
    drop potentially valuable queries.
    """
    if domain_visible is None:
        return 0.7
    if not domain_visible:
        return 1.0
    if visibility_position is None:
        return 0.3
    if visibility_position <= 1:
        return 0.0
    return _clip((visibility_position - 1) / 10.0)


def intent_weight(search_intent: str | None) -> float:
    if not search_intent:
        return INTENT_WEIGHTS["informational"]
    return INTENT_WEIGHTS.get(search_intent.lower(), INTENT_WEIGHTS["informational"])


def opportunity_score(
    search_volume: int | float | None,
    competitive_difficulty: int | float | None,
    domain_visible: bool | None,
    visibility_position: int | None = None,
    search_intent: str | None = None,
) -> float:
    """Return a 0.0–1.0 opportunity score.

    score = 0.35 * volume_norm
          + 0.25 * (1 - difficulty/100)
          + 0.25 * visibility_gap
          + 0.15 * intent_weight
    """
    score = (
        WEIGHT_VOLUME * volume_norm(search_volume)
        + WEIGHT_EASE * ease_score(competitive_difficulty)
        + WEIGHT_GAP * visibility_gap(domain_visible, visibility_position)
        + WEIGHT_INTENT * intent_weight(search_intent)
    )
    return round(_clip(score), 4)
