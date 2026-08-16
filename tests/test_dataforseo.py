"""DataForSEO visibility parsing tests (HTTP mocked)."""

from __future__ import annotations

from app.services.dataforseo import DataForSEOClient


def test_organic_rank_counts_as_visible(monkeypatch):
    client = DataForSEOClient(login="user", password="pass")

    def fake_post(path, payload):
        return {
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "domain": "www.surferseo.com",
                                    "rank_group": 3,
                                }
                            ]
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    result = client.check_visibility("best seo tool", "surferseo.com", "Surfer SEO")
    assert result.domain_visible is True
    assert result.visibility_position == 3
    assert result.visibility_status == "visible"
    assert result.source == "organic"


def test_ai_overview_citation_counts_as_visible(monkeypatch):
    client = DataForSEOClient(login="user", password="pass")

    def fake_post(path, payload):
        return {
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "domain": "clearscope.io",
                                    "rank_group": 1,
                                },
                                {
                                    "type": "ai_overview",
                                    "markdown": "Several tools exist.",
                                    "references": [
                                        {"domain": "marketmuse.com"},
                                        {"domain": "surferseo.com", "url": "https://surferseo.com/blog"},
                                    ],
                                },
                            ]
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    result = client.check_visibility("best seo tool", "surferseo.com", "Surfer SEO")
    assert result.domain_visible is True
    assert result.visibility_position == 2
    assert result.source == "ai_overview"


def test_missing_domain_is_not_visible(monkeypatch):
    client = DataForSEOClient(login="user", password="pass")

    def fake_post(path, payload):
        return {
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [
                        {
                            "items": [
                                {"type": "organic", "domain": "clearscope.io", "rank_group": 1}
                            ]
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    result = client.check_visibility("best seo tool", "surferseo.com", "Surfer SEO")
    assert result.domain_visible is False
    assert result.visibility_status == "not_visible"
