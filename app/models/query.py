"""A commercially relevant query discovered and scored for a profile."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import utcnow
from app.models.guid import GUID


class DiscoveredQuery(db.Model):
    __tablename__ = "discovered_queries"
    __table_args__ = (
        Index("ix_discovered_queries_profile_score", "profile_uuid", "opportunity_score"),
    )

    uuid: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_uuid: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("business_profiles.uuid"), nullable=False, index=True
    )
    run_uuid: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("pipeline_runs.uuid"), nullable=False, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    seed_keyword: Mapped[str | None] = mapped_column(String(80), nullable=True)
    estimated_search_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    competitive_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    domain_visible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    visibility_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visibility_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    search_intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    commercial_intent_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.45)
    discovered_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    profile = relationship("BusinessProfile", back_populates="queries")
    run = relationship("PipelineRun", back_populates="queries")
    recommendations = relationship(
        "ContentRecommendation",
        back_populates="target_query",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
