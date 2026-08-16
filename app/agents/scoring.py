"""Agent 2 — Visibility Scoring.

Uses DataForSEO (not the LLM) for search volume, keyword difficulty,
search intent, and whether the target domain appears in Google organic
results or AI Overview citations. Opportunity score is computed locally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.schemas import DiscoveredQueryItem
from app.services.dataforseo import (
    DataForSEOClient,
    DataForSEOError,
    KeywordMetrics,
    VisibilityResult,
)
from app.utils.scoring import INTENT_WEIGHTS, intent_weight, opportunity_score

VALID_INTENTS = set(INTENT_WEIGHTS)

logger = logging.getLogger("app.agents.scoring")


def _coerce_intent(value: str | None) -> str:
    if value and value.lower() in VALID_INTENTS:
        return value.lower()
    return "commercial"


@dataclass
class ScoredQuery:
    query_text: str
    seed_keyword: str
    estimated_search_volume: int
    competitive_difficulty: int
    search_intent: str
    commercial_intent_score: float
    domain_visible: bool | None
    visibility_position: int | None
    visibility_status: str
    opportunity_score: float


class VisibilityScoringAgent:
    name = "visibility_scoring"

    def __init__(self, client: DataForSEOClient | None = None) -> None:
        self.client = client or DataForSEOClient()
        self.last_tokens = 0  # no LLM tokens; kept for a uniform agent interface

    def score_queries(
        self,
        queries: list[DiscoveredQueryItem],
        domain: str,
        brand_name: str,
        run_uuid: str = "-",
    ) -> list[ScoredQuery]:
        extra = {"run_uuid": run_uuid}
        seeds = [item.seed_keyword or item.query_text[:80] for item in queries]

        metrics_by_seed: dict[str, KeywordMetrics] = {}
        try:
            metrics_by_seed = self.client.fetch_keyword_metrics(seeds)
        except DataForSEOError:
            logger.exception("scoring.bulk_metrics_failed", extra=extra)

        visibilities = self._visibility_with_isolation(
            [item.query_text for item in queries],
            domain,
            brand_name,
            extra,
        )

        scored: list[ScoredQuery] = []
        for index, item in enumerate(queries):
            seed_key = (item.seed_keyword or "").strip().lower()
            metrics = metrics_by_seed.get(seed_key, KeywordMetrics())
            visibility = visibilities[index] if index < len(visibilities) else VisibilityResult(
                domain_visible=None,
                visibility_position=None,
                visibility_status="unknown",
            )
            intent = _coerce_intent(metrics.search_intent or item.intent_hint)
            intent_score = intent_weight(intent)

            score = opportunity_score(
                search_volume=metrics.search_volume,
                competitive_difficulty=metrics.competitive_difficulty,
                domain_visible=visibility.domain_visible,
                visibility_position=visibility.visibility_position,
                search_intent=intent,
            )
            scored.append(
                ScoredQuery(
                    query_text=item.query_text,
                    seed_keyword=item.seed_keyword,
                    estimated_search_volume=metrics.search_volume,
                    competitive_difficulty=metrics.competitive_difficulty,
                    search_intent=intent,
                    commercial_intent_score=round(float(intent_score), 4),
                    domain_visible=visibility.domain_visible,
                    visibility_position=visibility.visibility_position,
                    visibility_status=visibility.visibility_status,
                    opportunity_score=score,
                )
            )
        return scored

    def score_single(
        self,
        query_text: str,
        seed_keyword: str,
        domain: str,
        brand_name: str,
        intent_hint: str = "commercial",
        run_uuid: str = "-",
    ) -> ScoredQuery:
        item = DiscoveredQueryItem(
            query_text=query_text,
            seed_keyword=seed_keyword or query_text[:80],
            intent_hint=_coerce_intent(intent_hint),  # type: ignore[arg-type]
        )
        results = self.score_queries([item], domain, brand_name, run_uuid=run_uuid)
        return results[0]

    def _visibility_with_isolation(
        self,
        query_texts: list[str],
        domain: str,
        brand_name: str,
        extra: dict,
    ) -> list[VisibilityResult]:
        try:
            return self.client.check_visibility_batch(query_texts, domain, brand_name)
        except Exception:
            logger.exception("scoring.visibility_batch_failed", extra=extra)
            results: list[VisibilityResult] = []
            for query in query_texts:
                try:
                    results.append(self.client.check_visibility(query, domain, brand_name))
                except Exception:
                    logger.exception(
                        "scoring.visibility_item_failed query=%s", query, extra=extra
                    )
                    results.append(
                        VisibilityResult(
                            domain_visible=None,
                            visibility_position=None,
                            visibility_status="unknown",
                        )
                    )
            return results
