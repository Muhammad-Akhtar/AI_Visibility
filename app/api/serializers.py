"""Serialize SQLAlchemy models into API JSON."""

from __future__ import annotations

from app.models import BusinessProfile, ContentRecommendation, DiscoveredQuery, PipelineRun
from app.utils.time import isoformat_z


def serialize_profile(profile: BusinessProfile, extra: dict | None = None) -> dict:
    payload = {
        "profile_uuid": str(profile.uuid),
        "name": profile.name,
        "domain": profile.domain,
        "industry": profile.industry,
        "description": profile.description,
        "competitors": profile.competitors or [],
        "status": profile.status,
        "created_at": isoformat_z(profile.created_at),
        "updated_at": isoformat_z(profile.updated_at),
    }
    if extra:
        payload.update(extra)
    return payload


def serialize_query(query: DiscoveredQuery) -> dict:
    return {
        "query_uuid": str(query.uuid),
        "query_text": query.query_text,
        "estimated_search_volume": query.estimated_search_volume,
        "competitive_difficulty": query.competitive_difficulty,
        "opportunity_score": query.opportunity_score,
        "domain_visible": query.domain_visible if query.domain_visible is not None else False,
        "visibility_position": query.visibility_position,
        "visibility_status": query.visibility_status,
        "search_intent": query.search_intent,
        "discovered_at": isoformat_z(query.discovered_at),
    }


def serialize_recommendation(rec: ContentRecommendation) -> dict:
    return {
        "recommendation_uuid": str(rec.uuid),
        "target_query_uuid": str(rec.query_uuid),
        "content_type": rec.content_type,
        "title": rec.title,
        "rationale": rec.rationale,
        "target_keywords": rec.target_keywords or [],
        "priority": rec.priority,
        "created_at": isoformat_z(rec.created_at),
    }


def serialize_run_summary(
    run: PipelineRun,
    top_queries: list[DiscoveredQuery],
    recommendations: list[ContentRecommendation],
) -> dict:
    return {
        "pipeline_run_uuid": str(run.uuid),
        "status": run.status,
        "queries_discovered": run.queries_discovered,
        "queries_scored": run.queries_scored,
        "top_opportunity_queries": [serialize_query(query) for query in top_queries],
        "recommendations": [serialize_recommendation(rec) for rec in recommendations],
        "tokens_used": run.tokens_used,
        "error_message": run.error_message,
        "started_at": isoformat_z(run.started_at),
        "completed_at": isoformat_z(run.completed_at),
    }
