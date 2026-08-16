"""Profiles API: register, inspect, run pipeline, list queries and recommendations."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from sqlalchemy import func

from app.api.serializers import (
    serialize_profile,
    serialize_query,
    serialize_recommendation,
    serialize_run_summary,
)
from app.errors import APIError, format_pydantic_error
from app.extensions import db, limiter
from app.models import BusinessProfile, ContentRecommendation, DiscoveredQuery
from app.schemas import ProfileCreate
from app.services.pipeline import Pipeline

profiles_bp = Blueprint("profiles", __name__)

ALLOWED_VISIBILITY = {"visible", "not_visible", "unknown"}


def _parse_uuid(value: str, label: str = "uuid") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise APIError("invalid_uuid", f"Invalid {label}", 400) from exc


def _get_profile(profile_uuid: str) -> BusinessProfile:
    parsed = _parse_uuid(profile_uuid, "profile_uuid")
    profile = db.session.get(BusinessProfile, parsed)
    if profile is None:
        raise APIError("not_found", "Profile not found", 404)
    return profile


@profiles_bp.route("", methods=["POST"])
@profiles_bp.route("/", methods=["POST"])
def create_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("validation_error", "JSON object body is required", 400)
    try:
        payload = ProfileCreate.model_validate(data)
    except ValidationError as exc:
        raise APIError("validation_error", format_pydantic_error(exc), 400) from exc

    profile = BusinessProfile(
        name=payload.name,
        domain=payload.domain,
        industry=payload.industry,
        description=payload.description,
        competitors=payload.competitors,
        status="created",
    )
    db.session.add(profile)
    db.session.commit()
    return (
        jsonify(
            {
                "profile_uuid": str(profile.uuid),
                "name": profile.name,
                "domain": profile.domain,
                "status": profile.status,
                "created_at": serialize_profile(profile)["created_at"],
            }
        ),
        201,
    )


@profiles_bp.route("/<profile_uuid>", methods=["GET"])
def get_profile(profile_uuid: str):
    profile = _get_profile(profile_uuid)
    total = (
        db.session.query(func.count(DiscoveredQuery.uuid))
        .filter(DiscoveredQuery.profile_uuid == profile.uuid)
        .scalar()
        or 0
    )
    avg_score = (
        db.session.query(func.avg(DiscoveredQuery.opportunity_score))
        .filter(DiscoveredQuery.profile_uuid == profile.uuid)
        .scalar()
    )
    return jsonify(
        serialize_profile(
            profile,
            extra={
                "total_queries": int(total),
                "avg_opportunity_score": round(float(avg_score), 4) if avg_score is not None else None,
            },
        )
    )


@profiles_bp.route("/<profile_uuid>/run", methods=["POST"])
@limiter.limit("5 per hour")
def run_pipeline(profile_uuid: str):
    profile = _get_profile(profile_uuid)
    run = Pipeline().run(profile)
    top_queries = (
        db.session.query(DiscoveredQuery)
        .filter_by(run_uuid=run.uuid)
        .order_by(DiscoveredQuery.opportunity_score.desc())
        .limit(3)
        .all()
    )
    recommendations = (
        db.session.query(ContentRecommendation)
        .filter_by(run_uuid=run.uuid)
        .order_by(ContentRecommendation.created_at.asc())
        .all()
    )
    return jsonify(serialize_run_summary(run, top_queries, recommendations))


@profiles_bp.route("/<profile_uuid>/queries", methods=["GET"])
def list_queries(profile_uuid: str):
    profile = _get_profile(profile_uuid)

    min_score = request.args.get("min_score", type=float)
    status = request.args.get("status", type=str)
    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=20, type=int) or 20
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)

    if status and status not in ALLOWED_VISIBILITY:
        raise APIError(
            "validation_error",
            "status must be one of visible, not_visible, unknown",
            400,
        )

    query = db.session.query(DiscoveredQuery).filter_by(profile_uuid=profile.uuid)
    if min_score is not None:
        query = query.filter(DiscoveredQuery.opportunity_score >= min_score)
    if status:
        query = query.filter(DiscoveredQuery.visibility_status == status)

    query = query.order_by(DiscoveredQuery.opportunity_score.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(
        {
            "queries": [serialize_query(row) for row in rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
            },
        }
    )


@profiles_bp.route("/<profile_uuid>/recommendations", methods=["GET"])
def list_recommendations(profile_uuid: str):
    profile = _get_profile(profile_uuid)
    rows = (
        db.session.query(ContentRecommendation)
        .filter_by(profile_uuid=profile.uuid)
        .order_by(ContentRecommendation.created_at.desc())
        .all()
    )
    return jsonify({"recommendations": [serialize_recommendation(row) for row in rows]})
