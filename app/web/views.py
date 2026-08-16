"""HTML views for the AI Visibility Intelligence UI."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from pydantic import ValidationError
from sqlalchemy import func
from werkzeug.exceptions import NotFound

from app.errors import format_pydantic_error
from app.extensions import db
from app.models import BusinessProfile, ContentRecommendation, DiscoveredQuery, PipelineRun
from app.schemas import ProfileCreate

web_bp = Blueprint("web", __name__)

ALLOWED_VISIBILITY = {"visible", "not_visible", "unknown"}
CONTENT_TYPE_LABELS = {
    "blog_post": "Blog post",
    "landing_page": "Landing page",
    "faq": "FAQ",
    "comparison_guide": "Comparison guide",
    "case_study": "Case study",
}
PRIORITY_ORDER = ("high", "medium", "low")


def _parse_uuid(value: str, label: str = "Profile") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise NotFound(f"{label} not found") from exc


def _get_profile(profile_uuid: str) -> BusinessProfile:
    profile = db.session.get(BusinessProfile, _parse_uuid(profile_uuid))
    if profile is None:
        raise NotFound("Profile not found")
    return profile


def _parse_competitors(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def _visibility_counts(profile_uuid: uuid.UUID) -> dict[str, int]:
    rows = (
        db.session.query(DiscoveredQuery.visibility_status, func.count(DiscoveredQuery.uuid))
        .filter(DiscoveredQuery.profile_uuid == profile_uuid)
        .group_by(DiscoveredQuery.visibility_status)
        .all()
    )
    counts = {"visible": 0, "not_visible": 0, "unknown": 0}
    for status, total in rows:
        if status in counts:
            counts[status] = int(total)
    return counts


def _profile_cards() -> list[dict]:
    profiles = (
        db.session.query(BusinessProfile).order_by(BusinessProfile.created_at.desc()).all()
    )
    if not profiles:
        return []

    ids = [row.uuid for row in profiles]
    stats_rows = (
        db.session.query(
            DiscoveredQuery.profile_uuid,
            func.count(DiscoveredQuery.uuid),
            func.avg(DiscoveredQuery.opportunity_score),
        )
        .filter(DiscoveredQuery.profile_uuid.in_(ids))
        .group_by(DiscoveredQuery.profile_uuid)
        .all()
    )
    stats = {
        profile_uuid: {
            "total_queries": int(total),
            "avg_opportunity_score": round(float(avg), 4) if avg is not None else None,
        }
        for profile_uuid, total, avg in stats_rows
    }

    runs = (
        db.session.query(PipelineRun)
        .filter(PipelineRun.profile_uuid.in_(ids))
        .order_by(PipelineRun.started_at.desc())
        .all()
    )
    latest: dict[uuid.UUID, PipelineRun] = {}
    for run in runs:
        latest.setdefault(run.profile_uuid, run)

    cards = []
    for profile in profiles:
        extra = stats.get(profile.uuid, {"total_queries": 0, "avg_opportunity_score": None})
        cards.append(
            {
                "profile": profile,
                "total_queries": extra["total_queries"],
                "avg_opportunity_score": extra["avg_opportunity_score"],
                "last_run": latest.get(profile.uuid),
            }
        )
    return cards


@web_bp.app_template_filter("human_dt")
def human_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


@web_bp.app_template_filter("pct")
def pct(score: float | None) -> str:
    if score is None:
        return "—"
    return str(int(round(float(score) * 100)))


@web_bp.app_template_filter("volume")
def volume(value: int | None) -> str:
    if value is None:
        return "—"
    number = int(value)
    if number >= 1_000_000:
        text = f"{number / 1_000_000:.1f}M"
    elif number >= 1000:
        text = f"{number / 1000:.1f}K"
    else:
        return str(number)
    return text.replace(".0M", "M").replace(".0K", "K")


@web_bp.app_template_filter("content_type_label")
def content_type_label(value: str | None) -> str:
    if not value:
        return "—"
    return CONTENT_TYPE_LABELS.get(value, value.replace("_", " ").title())


@web_bp.app_template_filter("status_label")
def status_label(value: str | None) -> str:
    labels = {
        "visible": "Visible",
        "not_visible": "Gap",
        "unknown": "Unknown",
        "created": "Created",
        "completed": "Completed",
        "failed": "Failed",
        "running": "Running",
    }
    return labels.get(value or "", (value or "—").replace("_", " ").title())


@web_bp.route("/")
def dashboard():
    return render_template("dashboard.html", nav="dashboard", cards=_profile_cards())


@web_bp.route("/profiles/new", methods=["GET", "POST"])
def new_profile():
    form = {
        "name": "",
        "domain": "",
        "industry": "",
        "description": "",
        "competitors": "",
    }
    error = None
    if request.method == "POST":
        form = {key: (request.form.get(key) or "").strip() for key in form}
        try:
            payload = ProfileCreate.model_validate(
                {
                    "name": form["name"],
                    "domain": form["domain"],
                    "industry": form["industry"],
                    "description": form["description"],
                    "competitors": _parse_competitors(form["competitors"]),
                }
            )
        except ValidationError as exc:
            return (
                render_template(
                    "profiles/new.html",
                    nav="new",
                    form=form,
                    error=format_pydantic_error(exc),
                ),
                400,
            )

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
        flash(f"{profile.name} is registered. Run the pipeline to discover queries.", "success")
        return redirect(url_for("web.profile_detail", profile_uuid=profile.uuid))

    return render_template("profiles/new.html", nav="new", form=form, error=error)


@web_bp.route("/profiles/<profile_uuid>")
def profile_detail(profile_uuid: str):
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
    last_run = (
        db.session.query(PipelineRun)
        .filter_by(profile_uuid=profile.uuid)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
    top_queries = (
        db.session.query(DiscoveredQuery)
        .filter_by(profile_uuid=profile.uuid)
        .order_by(DiscoveredQuery.opportunity_score.desc())
        .limit(3)
        .all()
    )
    recommendations = (
        db.session.query(ContentRecommendation)
        .filter_by(profile_uuid=profile.uuid)
        .order_by(ContentRecommendation.created_at.desc())
        .limit(3)
        .all()
    )
    recent_runs = (
        db.session.query(PipelineRun)
        .filter_by(profile_uuid=profile.uuid)
        .order_by(PipelineRun.started_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "profiles/detail.html",
        nav="overview",
        profile=profile,
        total_queries=int(total),
        avg_opportunity_score=round(float(avg_score), 4) if avg_score is not None else None,
        visibility=_visibility_counts(profile.uuid),
        last_run=last_run,
        top_queries=top_queries,
        recommendations=recommendations,
        recent_runs=recent_runs,
    )


@web_bp.route("/profiles/<profile_uuid>/queries")
def queries(profile_uuid: str):
    profile = _get_profile(profile_uuid)
    min_score = request.args.get("min_score", type=float)
    status = request.args.get("status", type=str) or ""
    page = request.args.get("page", default=1, type=int) or 1
    per_page = 20
    page = max(page, 1)

    query = db.session.query(DiscoveredQuery).filter_by(profile_uuid=profile.uuid)
    if min_score is not None:
        query = query.filter(DiscoveredQuery.opportunity_score >= min_score)
    if status in ALLOWED_VISIBILITY:
        query = query.filter(DiscoveredQuery.visibility_status == status)
    else:
        status = ""

    query = query.order_by(DiscoveredQuery.opportunity_score.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    page_count = max((total + per_page - 1) // per_page, 1)
    filter_args: dict[str, float | str] = {}
    if min_score is not None:
        filter_args["min_score"] = min_score
    if status:
        filter_args["status"] = status
    return render_template(
        "queries/index.html",
        nav="queries",
        profile=profile,
        queries=rows,
        min_score=min_score,
        status=status,
        page=page,
        per_page=per_page,
        total=total,
        page_count=page_count,
        filter_args=filter_args,
    )


@web_bp.route("/profiles/<profile_uuid>/recommendations")
def recommendations(profile_uuid: str):
    profile = _get_profile(profile_uuid)
    rows = (
        db.session.query(ContentRecommendation, DiscoveredQuery)
        .join(DiscoveredQuery, ContentRecommendation.query_uuid == DiscoveredQuery.uuid)
        .filter(ContentRecommendation.profile_uuid == profile.uuid)
        .order_by(ContentRecommendation.created_at.desc())
        .all()
    )
    grouped: dict[str, list[dict]] = {key: [] for key in PRIORITY_ORDER}
    for rec, query in rows:
        bucket = rec.priority if rec.priority in grouped else "medium"
        grouped[bucket].append({"rec": rec, "query": query})
    return render_template(
        "recommendations/index.html",
        nav="recommendations",
        profile=profile,
        grouped=grouped,
        total=len(rows),
    )
