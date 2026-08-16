"""Initial schema for AI Visibility Intelligence API.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

from app.models.guid import GUID

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "business_profiles",
        sa.Column("uuid", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("competitors", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_business_profiles_domain", "business_profiles", ["domain"])

    op.create_table(
        "pipeline_runs",
        sa.Column("uuid", GUID(), nullable=False),
        sa.Column("profile_uuid", GUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("queries_discovered", sa.Integer(), nullable=False),
        sa.Column("queries_scored", sa.Integer(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_uuid"], ["business_profiles.uuid"]),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index("ix_pipeline_runs_profile_uuid", "pipeline_runs", ["profile_uuid"])

    op.create_table(
        "discovered_queries",
        sa.Column("uuid", GUID(), nullable=False),
        sa.Column("profile_uuid", GUID(), nullable=False),
        sa.Column("run_uuid", GUID(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("seed_keyword", sa.String(length=80), nullable=True),
        sa.Column("estimated_search_volume", sa.Integer(), nullable=False),
        sa.Column("competitive_difficulty", sa.Integer(), nullable=False),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column("domain_visible", sa.Boolean(), nullable=True),
        sa.Column("visibility_position", sa.Integer(), nullable=True),
        sa.Column("visibility_status", sa.String(length=20), nullable=False),
        sa.Column("search_intent", sa.String(length=50), nullable=True),
        sa.Column("commercial_intent_score", sa.Float(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_uuid"], ["business_profiles.uuid"]),
        sa.ForeignKeyConstraint(["run_uuid"], ["pipeline_runs.uuid"]),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index(
        "ix_discovered_queries_profile_uuid", "discovered_queries", ["profile_uuid"]
    )
    op.create_index("ix_discovered_queries_run_uuid", "discovered_queries", ["run_uuid"])
    op.create_index(
        "ix_discovered_queries_profile_score",
        "discovered_queries",
        ["profile_uuid", "opportunity_score"],
    )

    op.create_table(
        "content_recommendations",
        sa.Column("uuid", GUID(), nullable=False),
        sa.Column("profile_uuid", GUID(), nullable=False),
        sa.Column("query_uuid", GUID(), nullable=False),
        sa.Column("run_uuid", GUID(), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("target_keywords", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_uuid"], ["business_profiles.uuid"]),
        sa.ForeignKeyConstraint(["query_uuid"], ["discovered_queries.uuid"]),
        sa.ForeignKeyConstraint(["run_uuid"], ["pipeline_runs.uuid"]),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index(
        "ix_content_recommendations_profile_uuid",
        "content_recommendations",
        ["profile_uuid"],
    )
    op.create_index(
        "ix_content_recommendations_query_uuid",
        "content_recommendations",
        ["query_uuid"],
    )
    op.create_index(
        "ix_content_recommendations_run_uuid",
        "content_recommendations",
        ["run_uuid"],
    )


def downgrade():
    op.drop_index("ix_content_recommendations_run_uuid", table_name="content_recommendations")
    op.drop_index("ix_content_recommendations_query_uuid", table_name="content_recommendations")
    op.drop_index("ix_content_recommendations_profile_uuid", table_name="content_recommendations")
    op.drop_table("content_recommendations")
    op.drop_index("ix_discovered_queries_profile_score", table_name="discovered_queries")
    op.drop_index("ix_discovered_queries_run_uuid", table_name="discovered_queries")
    op.drop_index("ix_discovered_queries_profile_uuid", table_name="discovered_queries")
    op.drop_table("discovered_queries")
    op.drop_index("ix_pipeline_runs_profile_uuid", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_index("ix_business_profiles_domain", table_name="business_profiles")
    op.drop_table("business_profiles")
