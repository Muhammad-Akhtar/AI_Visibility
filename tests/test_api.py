"""HTTP API tests."""

from __future__ import annotations

from app.extensions import db
from app.models import DiscoveredQuery, PipelineRun
from app.services.pipeline import Pipeline
from tests.test_pipeline import FakeDiscovery, FakeRecommendation, FakeScoring


def test_create_profile_success(client):
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "Surfer SEO",
            "domain": "https://www.surferseo.com/pricing",
            "industry": "SEO Software",
            "description": "AI-powered SEO content optimization tool",
            "competitors": ["clearscope.io", "marketmuse.com", "frase.io"],
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["name"] == "Surfer SEO"
    assert body["domain"] == "surferseo.com"
    assert body["status"] == "created"
    assert "profile_uuid" in body
    assert body["created_at"].endswith("Z")


def test_create_profile_rejects_missing_domain(client):
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "Surfer SEO",
            "industry": "SEO Software",
            "description": "tool",
        },
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "validation_error"


def test_get_profile_not_found(client):
    response = client.get("/api/v1/profiles/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_get_profile_includes_summary_stats(client, profile):
    run = PipelineRun(
        profile_uuid=profile.uuid,
        status="completed",
        correlation_id="test",
        queries_discovered=1,
        queries_scored=1,
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(
        DiscoveredQuery(
            profile_uuid=profile.uuid,
            run_uuid=run.uuid,
            query_text="What is the best SEO content tool?",
            estimated_search_volume=1200,
            competitive_difficulty=40,
            opportunity_score=0.81,
            domain_visible=False,
            visibility_status="not_visible",
        )
    )
    db.session.commit()

    response = client.get(f"/api/v1/profiles/{profile.uuid}")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total_queries"] == 1
    assert body["avg_opportunity_score"] == 0.81


def test_run_pipeline_and_list_queries(client, profile, monkeypatch):
    monkeypatch.setattr(
        "app.api.profiles.Pipeline",
        lambda: Pipeline(
            discovery=FakeDiscovery(),
            scoring=FakeScoring(),
            recommendation=FakeRecommendation(),
        ),
    )
    response = client.post(f"/api/v1/profiles/{profile.uuid}/run")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "completed"
    assert body["queries_discovered"] == 2
    assert body["queries_scored"] == 2
    assert len(body["top_opportunity_queries"]) <= 3
    assert body["tokens_used"] == 20
    assert body["recommendations"]

    listed = client.get(f"/api/v1/profiles/{profile.uuid}/queries?min_score=0.7")
    assert listed.status_code == 200
    queries = listed.get_json()["queries"]
    assert len(queries) == 1
    assert queries[0]["opportunity_score"] >= 0.7

    filtered = client.get(f"/api/v1/profiles/{profile.uuid}/queries?status=unknown")
    assert len(filtered.get_json()["queries"]) == 1

    recs = client.get(f"/api/v1/profiles/{profile.uuid}/recommendations")
    assert recs.status_code == 200
    assert len(recs.get_json()["recommendations"]) == 1
    rec = recs.get_json()["recommendations"][0]
    assert rec["content_type"] == "blog_post"
    assert rec["priority"] == "high"
    assert rec["target_keywords"]


def test_query_status_filter_rejects_invalid_value(client, profile):
    response = client.get(f"/api/v1/profiles/{profile.uuid}/queries?status=nope")
    assert response.status_code == 400


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_recheck_query(client, profile, monkeypatch):
    monkeypatch.setattr(
        "app.api.queries.Pipeline",
        lambda: Pipeline(
            discovery=FakeDiscovery(),
            scoring=FakeScoring(),
            recommendation=FakeRecommendation(),
        ),
    )
    run = PipelineRun(
        profile_uuid=profile.uuid,
        status="completed",
        correlation_id="recheck",
    )
    db.session.add(run)
    db.session.flush()
    query = DiscoveredQuery(
        profile_uuid=profile.uuid,
        run_uuid=run.uuid,
        query_text="What is the best SEO content optimization tool?",
        seed_keyword="best seo content tool",
        estimated_search_volume=0,
        competitive_difficulty=50,
        opportunity_score=0.1,
        visibility_status="unknown",
    )
    db.session.add(query)
    db.session.commit()

    response = client.post(f"/api/v1/queries/{query.uuid}/recheck")
    assert response.status_code == 200
    body = response.get_json()
    assert body["estimated_search_volume"] == 1200
    assert body["visibility_status"] == "not_visible"
    assert body["opportunity_score"] == 0.81
