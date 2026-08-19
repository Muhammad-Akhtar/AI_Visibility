"""DataForSEO visibility parsing tests (HTTP mocked)."""

from __future__ import annotations

import httpx

from app.config import DATAFORSEO_PRODUCTION_BASE_URL
from app.services.dataforseo import (
    DataForSEOClient,
    SEARCH_VOLUME_PATH,
)


def test_client_defaults_to_production_base_url():
    client = DataForSEOClient(login="user", password="pass")
    assert client.base_url == DATAFORSEO_PRODUCTION_BASE_URL


def test_client_uses_sandbox_base_url_from_config(app):
    app.config["DATAFORSEO_BASE_URL"] = "https://sandbox.dataforseo.com/v3"
    with app.app_context():
        client = DataForSEOClient(login="user", password="pass")
    assert client.base_url == "https://sandbox.dataforseo.com/v3"


def test_post_uses_configured_base_url(app, monkeypatch):
    app.config["DATAFORSEO_BASE_URL"] = "https://sandbox.dataforseo.com/v3"
    captured: dict[str, str] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"tasks": [{"status_code": 20000, "result": []}]}

        text = ""

    def fake_post(url, **kwargs):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with app.app_context():
        client = DataForSEOClient(login="user", password="pass")
        client.fetch_search_volume(["best seo tool"])

    assert captured["url"] == f"https://sandbox.dataforseo.com/v3{SEARCH_VOLUME_PATH}"


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
