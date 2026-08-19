"""Pipeline orchestrator tests with mocked agents."""

from __future__ import annotations

from app.agents.scoring import ScoredQuery
from app.extensions import db
from app.models import ContentRecommendation, DiscoveredQuery, PipelineRun
from app.schemas import DiscoveredQueryItem, RecommendationItem
from app.services.pipeline import Pipeline


class FakeDiscovery:
    last_tokens = 11

    def discover(self, profile, run_uuid="-"):
        return [
            DiscoveredQueryItem(
                query_text="What is the best SEO content optimization tool?",
                seed_keyword="best seo content tool",
                intent_hint="commercial",
            ),
            DiscoveredQueryItem(
                query_text="Surfer SEO vs Clearscope which is better?",
                seed_keyword="surfer seo vs clearscope",
                intent_hint="commercial",
            ),
        ]


class FakeScoring:
    last_tokens = 0

    def score_queries(self, queries, domain, brand_name, run_uuid="-"):
        results = []
        for index, item in enumerate(queries):
            if "Clearscope" in item.query_text:
                results.append(
                    ScoredQuery(
                        query_text=item.query_text,
                        seed_keyword=item.seed_keyword,
                        estimated_search_volume=800,
                        competitive_difficulty=55,
                        search_intent="commercial",
                        commercial_intent_score=0.85,
                        domain_visible=None,
                        visibility_position=None,
                        visibility_status="unknown",
                        opportunity_score=0.42,
                    )
                )
                continue
            results.append(
                ScoredQuery(
                    query_text=item.query_text,
                    seed_keyword=item.seed_keyword,
                    estimated_search_volume=1200,
                    competitive_difficulty=40,
                    search_intent="commercial",
                    commercial_intent_score=0.85,
                    domain_visible=False,
                    visibility_position=None,
                    visibility_status="not_visible",
                    opportunity_score=0.81,
                )
            )
        return results

    def score_single(self, **kwargs):
        return self.score_queries(
            [
                DiscoveredQueryItem(
                    query_text=kwargs["query_text"],
                    seed_keyword=kwargs["seed_keyword"],
                    intent_hint="commercial",
                )
            ],
            kwargs["domain"],
            kwargs["brand_name"],
        )[0]


class FakeRecommendation:
    last_tokens = 9

    def recommend(self, profile, gap_queries, run_uuid="-"):
        return [
            RecommendationItem(
                target_query_index=0,
                target_query_text=gap_queries[0].query_text,
                content_type="blog_post",
                title="Best SEO Content Optimization Tools Compared",
                rationale="A roundup page gives AI assistants a citable source that names the brand for this high-volume commercial query.",
                target_keywords=["seo content tool", "content optimization software"],
                priority="high",
            )
        ]


class ExplodingDiscovery:
    last_tokens = 0

    def discover(self, profile, run_uuid="-"):
        raise RuntimeError("openai down")


def test_pipeline_persists_partial_scoring_and_recommendations(app, profile):
    pipeline = Pipeline(
        discovery=FakeDiscovery(),
        scoring=FakeScoring(),
        recommendation=FakeRecommendation(),
    )
    run = pipeline.run(profile)

    assert run.status == "completed"
    assert run.queries_discovered == 2
    assert run.queries_scored == 2
    assert run.tokens_used == 20

    queries = db.session.query(DiscoveredQuery).filter_by(profile_uuid=profile.uuid).all()
    assert len(queries) == 2
    statuses = {row.visibility_status for row in queries}
    assert "not_visible" in statuses
    assert "unknown" in statuses

    recs = db.session.query(ContentRecommendation).filter_by(profile_uuid=profile.uuid).all()
    assert len(recs) == 1
    assert recs[0].priority == "high"
    db.session.refresh(profile)
    assert profile.status == "processed"


def test_pipeline_skips_agent3_for_unknown_queries(app, profile):
    class UnknownOnlyScoring:
        last_tokens = 0

        def score_queries(self, queries, domain, brand_name, run_uuid="-"):
            return [
                ScoredQuery(
                    query_text=item.query_text,
                    seed_keyword=item.seed_keyword,
                    estimated_search_volume=500,
                    competitive_difficulty=40,
                    search_intent="commercial",
                    commercial_intent_score=0.85,
                    domain_visible=None,
                    visibility_position=None,
                    visibility_status="unknown",
                    opportunity_score=0.65,
                )
                for item in queries
            ]

    pipeline = Pipeline(
        discovery=FakeDiscovery(),
        scoring=UnknownOnlyScoring(),
        recommendation=FakeRecommendation(),
    )
    run = pipeline.run(profile)
    assert run.status == "completed"
    recs = db.session.query(ContentRecommendation).filter_by(profile_uuid=profile.uuid).all()
    assert len(recs) == 0


def test_pipeline_marks_failed_when_discovery_raises(app, profile):
    pipeline = Pipeline(
        discovery=ExplodingDiscovery(),
        scoring=FakeScoring(),
        recommendation=FakeRecommendation(),
    )
    run = pipeline.run(profile)
    assert run.status == "failed"
    assert run.error_message
    assert db.session.query(PipelineRun).count() == 1
    assert db.session.query(DiscoveredQuery).count() == 0
