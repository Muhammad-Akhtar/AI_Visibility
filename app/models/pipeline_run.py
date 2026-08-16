"""A single execution of the three-agent pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import utcnow
from app.models.guid import GUID


class PipelineRun(db.Model):
    __tablename__ = "pipeline_runs"

    uuid: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_uuid: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("business_profiles.uuid"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    queries_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queries_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = mapped_column(DateTime(timezone=True), nullable=True)

    profile = relationship("BusinessProfile", back_populates="runs")
    queries = relationship(
        "DiscoveredQuery",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    recommendations = relationship(
        "ContentRecommendation",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
