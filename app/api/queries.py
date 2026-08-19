"""Query-level endpoints (recheck a single scored query)."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify

from app.api.serializers import serialize_query
from app.errors import APIError
from app.extensions import db, limiter
from app.models import BusinessProfile, DiscoveredQuery
from app.services.pipeline import Pipeline
from app.utils.api_debug import (
    end_pipeline_log,
    print_api_request,
    print_api_response,
    start_pipeline_log,
)

queries_bp = Blueprint("queries", __name__)


@queries_bp.route("/<query_uuid>/recheck", methods=["POST"])
@limiter.limit("20 per hour")
def recheck_query(query_uuid: str):
    start_pipeline_log(mode="recheck", run_id=query_uuid, query_uuid=query_uuid)
    try:
        print_api_request(
            provider="Internal (Flask)",
            operation="Recheck Query",
            method="POST",
            url=f"/api/v1/queries/{query_uuid}/recheck",
            payload={"query_uuid": query_uuid},
        )
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
        response_body = serialize_query(updated)
        print_api_response(
            provider="Internal (Flask)",
            operation="Recheck Query",
            url=f"/api/v1/queries/{query_uuid}/recheck",
            status=200,
            response=response_body,
        )
        return jsonify(response_body)
    finally:
        end_pipeline_log()
