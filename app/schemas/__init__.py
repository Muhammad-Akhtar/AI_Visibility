"""Pydantic schemas for API requests and LLM structured output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.domain import normalize_domain


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    industry: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    competitors: list[str] = Field(default_factory=list)

    @field_validator("name", "industry", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("competitors")
    @classmethod
    def clean_competitors(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            if not item or not str(item).strip():
                continue
            cleaned.append(normalize_domain(str(item)))
        return cleaned


IntentHint = Literal["commercial", "transactional", "informational", "navigational"]


class DiscoveredQueryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query_text: str = Field(min_length=8)
    seed_keyword: str = Field(min_length=2, max_length=80)
    intent_hint: IntentHint = "commercial"

    @field_validator("query_text", "seed_keyword")
    @classmethod
    def strip_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("seed_keyword")
    @classmethod
    def limit_seed_words(cls, value: str) -> str:
        words = value.split()
        if len(words) > 10:
            value = " ".join(words[:10])
        return value[:80]


class DiscoveryOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    queries: list[DiscoveredQueryItem] = Field(min_length=1)


ContentType = Literal[
    "blog_post",
    "landing_page",
    "faq",
    "comparison_guide",
    "case_study",
]
Priority = Literal["high", "medium", "low"]


class RecommendationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_query_index: int = Field(ge=0)
    target_query_text: str = Field(default="")
    content_type: ContentType
    title: str = Field(min_length=8, max_length=500)
    rationale: str = Field(min_length=20)
    target_keywords: list[str] = Field(min_length=1)
    priority: Priority

    @field_validator("target_keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and str(item).strip()]
        if not cleaned:
            raise ValueError("target_keywords must contain at least one keyword")
        return cleaned


class RecommendationOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recommendations: list[RecommendationItem] = Field(default_factory=list)
