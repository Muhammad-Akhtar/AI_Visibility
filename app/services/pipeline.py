"""Pipeline orchestrator: Agent 1 → Agent 2 → Agent 3 with persistence."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agents.base import AgentOutputError
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.agents.scoring import ScoredQuery, VisibilityScoringAgent
from app.extensions import db
from app.models import BusinessProfile, ContentRecommendation, DiscoveredQuery, PipelineRun
from app.models.base import utcnow
from app.schemas import DiscoveredQueryItem, RecommendationItem

logger = logging.getLogger("app.pipeline")

MAX_GAP_QUERIES = 10


def _profile_payload(profile: BusinessProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "domain": profile.domain,
        "industry": profile.industry,
        "description": profile.description,
        "competitors": profile.competitors or [],
    }


def _match_gap_query(
    item: RecommendationItem, gap_queries: list[DiscoveredQuery]
) -> DiscoveredQuery | None:
    if item.target_query_text:
        wanted = item.target_query_text.strip().lower()
        for query in gap_queries:
            if query.query_text.strip().lower() == wanted:
                return query
    if 0 <= item.target_query_index < len(gap_queries):
        return gap_queries[item.target_query_index]
    return None


class Pipeline:
    """Coordinates the three agents and writes results to the database."""

    def __init__(
        self,
        discovery: QueryDiscoveryAgent | None = None,
        scoring: VisibilityScoringAgent | None = None,
        recommendation: ContentRecommendationAgent | None = None,
    ) -> None:
        self.discovery = discovery or QueryDiscoveryAgent()
        self.scoring = scoring or VisibilityScoringAgent()
        self.recommendation = recommendation or ContentRecommendationAgent()

    def run(self, profile: BusinessProfile) -> PipelineRun:
        run = PipelineRun(
            uuid=uuid.uuid4(),
            profile_uuid=profile.uuid,
            status="running",
            correlation_id="",
            started_at=utcnow(),
        )
        run.correlation_id = str(run.uuid)
        db.session.add(run)
        db.session.commit()

        extra = {"run_uuid": run.correlation_id}
        logger.info("pipeline.start profile=%s", profile.uuid, extra=extra)
        payload = _profile_payload(profile)

        try:
            discovered = self._run_discovery(payload, run, extra)
            scored_rows = self._run_scoring(discovered, profile, run, extra)
            self._run_recommendations(payload, scored_rows, profile, run, extra)

            run.status = "completed"
            profile.status = "processed"
            profile.updated_at = utcnow()
            logger.info(
                "pipeline.complete discovered=%s scored=%s tokens=%s",
                run.queries_discovered,
                run.queries_scored,
                run.tokens_used,
                extra=extra,
            )
        except Exception as exc:
            logger.exception("pipeline.failed", extra=extra)
            run.status = "failed"
            run.error_message = str(exc)
        finally:
            run.completed_at = utcnow()
            db.session.commit()

        return run

    def recheck_query(self, query: DiscoveredQuery, profile: BusinessProfile) -> DiscoveredQuery:
        extra = {"run_uuid": str(query.run_uuid)}
        logger.info("pipeline.recheck query=%s", query.uuid, extra=extra)
        scored = self.scoring.score_single(
            query_text=query.query_text,
            seed_keyword=query.seed_keyword or query.query_text[:80],
            domain=profile.domain,
            brand_name=profile.name,
            intent_hint=query.search_intent or "commercial",
            run_uuid=str(query.run_uuid),
        )
        query.estimated_search_volume = scored.estimated_search_volume
        query.competitive_difficulty = scored.competitive_difficulty
        query.search_intent = scored.search_intent
        query.commercial_intent_score = scored.commercial_intent_score
        query.domain_visible = scored.domain_visible
        query.visibility_position = scored.visibility_position
        query.visibility_status = scored.visibility_status
        query.opportunity_score = scored.opportunity_score
        db.session.commit()
        return query

    def _run_discovery(
        self,
        payload: dict[str, Any],
        run: PipelineRun,
        extra: dict,
    ) -> list[DiscoveredQueryItem]:
        logger.info("pipeline.agent1.start", extra=extra)
        discovered = self.discovery.discover(payload, run_uuid=run.correlation_id)
        run.tokens_used += int(self.discovery.last_tokens or 0)
        run.queries_discovered = len(discovered)
        db.session.commit()
        logger.info(
            "pipeline.agent1.complete count=%s tokens=%s",
            len(discovered),
            self.discovery.last_tokens,
            extra=extra,
        )
        if not discovered:
            raise AgentOutputError("Query Discovery Agent returned no queries")
        return discovered

    def _run_scoring(
        self,
        discovered: list[DiscoveredQueryItem],
        profile: BusinessProfile,
        run: PipelineRun,
        extra: dict,
    ) -> list[DiscoveredQuery]:
        logger.info("pipeline.agent2.start count=%s", len(discovered), extra=extra)
        try:
            scored = self.scoring.score_queries(
                discovered,
                domain=profile.domain,
                brand_name=profile.name,
                run_uuid=run.correlation_id,
            )
        except Exception:
            logger.exception("pipeline.agent2.batch_failed falling_back", extra=extra)
            scored = self._score_one_by_one(discovered, profile, extra)

        rows: list[DiscoveredQuery] = []
        scored_count = 0
        for item in scored:
            row = DiscoveredQuery(
                profile_uuid=profile.uuid,
                run_uuid=run.uuid,
                query_text=item.query_text,
                seed_keyword=item.seed_keyword,
                estimated_search_volume=item.estimated_search_volume,
                competitive_difficulty=item.competitive_difficulty,
                opportunity_score=item.opportunity_score,
                domain_visible=item.domain_visible,
                visibility_position=item.visibility_position,
                visibility_status=item.visibility_status,
                search_intent=item.search_intent,
                commercial_intent_score=item.commercial_intent_score,
            )
            if item.visibility_status != "unknown":
                scored_count += 1
            else:
                scored_count += 1  # still persisted with a computed score
            db.session.add(row)
            rows.append(row)

        run.queries_scored = scored_count
        db.session.commit()
        logger.info("pipeline.agent2.complete scored=%s", scored_count, extra=extra)
        return rows

    def _score_one_by_one(
        self,
        discovered: list[DiscoveredQueryItem],
        profile: BusinessProfile,
        extra: dict,
    ) -> list[ScoredQuery]:
        results: list[ScoredQuery] = []
        for item in discovered:
            try:
                results.append(
                    self.scoring.score_single(
                        query_text=item.query_text,
                        seed_keyword=item.seed_keyword,
                        domain=profile.domain,
                        brand_name=profile.name,
                        intent_hint=item.intent_hint,
                        run_uuid=extra.get("run_uuid", "-"),
                    )
                )
            except Exception:
                logger.exception(
                    "pipeline.agent2.item_failed query=%s", item.query_text, extra=extra
                )
                results.append(
                    ScoredQuery(
                        query_text=item.query_text,
                        seed_keyword=item.seed_keyword,
                        estimated_search_volume=0,
                        competitive_difficulty=50,
                        search_intent=item.intent_hint,
                        commercial_intent_score=0.45,
                        domain_visible=None,
                        visibility_position=None,
                        visibility_status="unknown",
                        opportunity_score=0.0,
                    )
                )
        return results

    def _run_recommendations(
        self,
        payload: dict[str, Any],
        scored_rows: list[DiscoveredQuery],
        profile: BusinessProfile,
        run: PipelineRun,
        extra: dict,
    ) -> None:
        gap_rows = [
            row
            for row in scored_rows
            if row.visibility_status == "not_visible" or row.domain_visible is False
        ]
        gap_rows.sort(key=lambda row: row.opportunity_score, reverse=True)
        gap_rows = gap_rows[:MAX_GAP_QUERIES]

        if not gap_rows:
            logger.info("pipeline.agent3.skip no_gap_queries", extra=extra)
            return

        gap_scored = [
            ScoredQuery(
                query_text=row.query_text,
                seed_keyword=row.seed_keyword or "",
                estimated_search_volume=row.estimated_search_volume,
                competitive_difficulty=row.competitive_difficulty,
                search_intent=row.search_intent or "informational",
                commercial_intent_score=row.commercial_intent_score,
                domain_visible=row.domain_visible,
                visibility_position=row.visibility_position,
                visibility_status=row.visibility_status,
                opportunity_score=row.opportunity_score,
            )
            for row in gap_rows
        ]

        logger.info("pipeline.agent3.start gaps=%s", len(gap_scored), extra=extra)
        try:
            recommendations = self.recommendation.recommend(
                payload, gap_scored, run_uuid=run.correlation_id
            )
        except Exception:
            logger.exception("pipeline.agent3.failed", extra=extra)
            run.error_message = (run.error_message or "") + " Agent 3 failed; queries were saved."
            return

        run.tokens_used += int(self.recommendation.last_tokens or 0)
        for item in recommendations:
            target = _match_gap_query(item, gap_rows)
            if target is None:
                continue
            db.session.add(
                ContentRecommendation(
                    profile_uuid=profile.uuid,
                    query_uuid=target.uuid,
                    run_uuid=run.uuid,
                    content_type=item.content_type,
                    title=item.title,
                    rationale=item.rationale,
                    target_keywords=item.target_keywords,
                    priority=item.priority,
                )
            )
        db.session.commit()
        logger.info(
            "pipeline.agent3.complete count=%s tokens=%s",
            len(recommendations),
            self.recommendation.last_tokens,
            extra=extra,
        )
