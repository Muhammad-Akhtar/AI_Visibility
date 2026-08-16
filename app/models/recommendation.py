"""Actionable content recommendation generated for a visibility gap."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.extensions import db
from app.models.base import utcnow
from app.models.guid import GUID


class ContentRecommendation(db.Model):
    __tablename__ = "content_recommendations"

    uuid: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_uuid: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("business_profiles.uuid"), nullable=False, index=True
    )
    query_uuid: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("discovered_queries.uuid"), nullable=False, index=True
    )
    run_uuid: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("pipeline_runs.uuid"), nullable=True, index=True
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    target_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    profile = relationship("BusinessProfile", back_populates="recommendations")
    target_query = relationship("DiscoveredQuery", back_populates="recommendations")
    run = relationship("PipelineRun", back_populates="recommendations")
