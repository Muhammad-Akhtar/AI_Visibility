"""Tests for pipeline agents using mocked LLM and DataForSEO responses."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.base import AgentOutputError, BaseAgent
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.agents.scoring import VisibilityScoringAgent
from app.schemas import DiscoveryOutput
from app.services.dataforseo import KeywordMetrics, VisibilityResult
from app.utils.json import JSONParseError, parse_llm_json
from app.utils.scoring import opportunity_score


class FakeCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0) if self.contents else "{}"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(total_tokens=12),
        )


def fake_openai(contents: list[str]):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(contents)))


DISCOVERY_JSON = {
    "queries": [
        {
            "query_text": "What is the best SEO content optimization tool?",
            "seed_keyword": "best seo content tool",
            "intent_hint": "commercial",
        },
        {
            "query_text": "How does Surfer SEO compare to Clearscope?",
            "seed_keyword": "surfer seo vs clearscope",
            "intent_hint": "commercial",
        },
    ]
}


class TestParseLlmJson:
    def test_parses_plain_object(self):
        assert parse_llm_json('{"queries": []}') == {"queries": []}

    def test_strips_markdown_fences(self):
        raw = "```json\n{\"ok\": true}\n```"
        assert parse_llm_json(raw) == {"ok": True}

    def test_extracts_object_from_prose(self):
        raw = 'Sure, here you go: {"ok": true} thanks'
        assert parse_llm_json(raw) == {"ok": True}

    def test_rejects_empty(self):
        with pytest.raises(JSONParseError):
            parse_llm_json("   ")


class TestBaseAgentJson:
    def test_validates_structured_output(self):
        agent = QueryDiscoveryAgent(client=fake_openai([json.dumps(DISCOVERY_JSON)]))
        result = agent.discover(
            {
                "name": "Surfer SEO",
                "domain": "surferseo.com",
                "industry": "SEO Software",
                "description": "SEO tool",
                "competitors": ["clearscope.io"],
            }
        )
        assert len(result) == 2
        assert result[0].seed_keyword == "best seo content tool"
        assert agent.last_tokens == 12

    def test_retries_on_malformed_json_then_succeeds(self):
        agent = BaseAgent(client=fake_openai(["not-json", json.dumps(DISCOVERY_JSON)]))
        parsed = agent.complete_json("sys", "user", DiscoveryOutput)
        assert len(parsed.queries) == 2
        assert agent.last_tokens == 24

    def test_raises_after_retry_still_invalid(self):
        agent = BaseAgent(client=fake_openai(["nope", "still nope"]))
        with pytest.raises(AgentOutputError):
            agent.complete_json("sys", "user", DiscoveryOutput)


class TestOpportunityScore:
    def test_high_volume_gap_outranks_already_visible(self):
        gap = opportunity_score(
            search_volume=5000,
            competitive_difficulty=30,
            domain_visible=False,
            visibility_position=None,
            search_intent="commercial",
        )
        owned = opportunity_score(
            search_volume=200,
            competitive_difficulty=80,
            domain_visible=True,
            visibility_position=1,
            search_intent="informational",
        )
        assert 0.0 <= owned < gap <= 1.0

    def test_commercial_beats_informational_all_else_equal(self):
        commercial = opportunity_score(1000, 50, False, None, "commercial")
        informational = opportunity_score(1000, 50, False, None, "informational")
        assert commercial > informational

    def test_unknown_visibility_is_between_gap_and_rank_one(self):
        unknown = opportunity_score(1000, 50, None, None, "commercial")
        gap = opportunity_score(1000, 50, False, None, "commercial")
        top = opportunity_score(1000, 50, True, 1, "commercial")
        assert top < unknown < gap


class FakeDataForSEO:
    def __init__(self) -> None:
        self.visibility_calls: list[str] = []

    def fetch_keyword_metrics(self, keywords):
        return {
            keyword.lower(): KeywordMetrics(
                search_volume=1200,
                competitive_difficulty=40,
                search_intent="commercial",
                intent_probability=0.9,
            )
            for keyword in keywords
        }

    def check_visibility_batch(self, queries, domain, brand_name=None, max_workers=4):
        results = []
        for query in queries:
            self.visibility_calls.append(query)
            if "broken" in query:
                results.append(
                    VisibilityResult(
                        domain_visible=None,
                        visibility_position=None,
                        visibility_status="unknown",
                    )
                )
            else:
                results.append(
                    VisibilityResult(
                        domain_visible=False,
                        visibility_position=None,
                        visibility_status="not_visible",
                    )
                )
        return results


class TestVisibilityScoringAgent:
    def test_continues_when_one_query_visibility_is_unknown(self):
        from app.schemas import DiscoveredQueryItem

        agent = VisibilityScoringAgent(client=FakeDataForSEO())
        queries = [
            DiscoveredQueryItem(
                query_text="What is the best SEO content tool?",
                seed_keyword="best seo content tool",
                intent_hint="commercial",
            ),
            DiscoveredQueryItem(
                query_text="This query is broken on purpose",
                seed_keyword="broken query",
                intent_hint="commercial",
            ),
        ]
        scored = agent.score_queries(queries, "surferseo.com", "Surfer SEO")
        assert len(scored) == 2
        assert scored[0].visibility_status == "not_visible"
        assert scored[1].visibility_status == "unknown"
        assert scored[0].opportunity_score > 0


class TestRecommendationAgent:
    def test_returns_empty_on_invalid_llm_output(self):
        from app.agents.scoring import ScoredQuery

        agent = ContentRecommendationAgent(client=fake_openai(["{", "{"]))
        gaps = [
            ScoredQuery(
                query_text="What is the best SEO content tool for teams?",
                seed_keyword="best seo content tool",
                estimated_search_volume=1200,
                competitive_difficulty=40,
                search_intent="commercial",
                commercial_intent_score=0.85,
                domain_visible=False,
                visibility_position=None,
                visibility_status="not_visible",
                opportunity_score=0.8,
            )
        ]
        result = agent.recommend(
            {
                "name": "Surfer",
                "domain": "surferseo.com",
                "industry": "SEO",
                "description": "tool",
                "competitors": [],
            },
            gaps,
        )
        assert result == []
