"""Query-level endpoints (recheck a single scored query)."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify

from app.api.serializers import serialize_query
from app.errors import APIError
from app.extensions import db, limiter
from app.models import BusinessProfile, DiscoveredQuery
from app.services.pipeline import Pipeline

queries_bp = Blueprint("queries", __name__)


@queries_bp.route("/<query_uuid>/recheck", methods=["POST"])
@limiter.limit("20 per hour")
def recheck_query(query_uuid: str):
    try:
        parsed = uuid.UUID(str(query_uuid))
    except ValueError as exc:
        raise APIError("invalid_uuid", "Invalid query_uuid", 400) from exc

    query = db.session.get(DiscoveredQuery, parsed)
    if query is None:
        raise APIError("not_found", "Query not found", 404)

    profile = db.session.get(BusinessProfile, query.profile_uuid)
    if profile is None:
        raise APIError("not_found", "Profile not found for this query", 404)

    updated = Pipeline().recheck_query(query, profile)
    return jsonify(serialize_query(updated))
