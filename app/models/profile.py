"""Business profile registered as the pipeline entry point."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.extensions import db
from app.models.base import utcnow
from app.models.guid import GUID


class BusinessProfile(db.Model):
    __tablename__ = "business_profiles"

    uuid: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    competitors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    runs = relationship(
        "PipelineRun",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    queries = relationship(
        "DiscoveredQuery",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    recommendations = relationship(
        "ContentRecommendation",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
