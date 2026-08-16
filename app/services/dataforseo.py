"""DataForSEO HTTP client for search volume, difficulty, intent, and SERP visibility."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import httpx
from flask import current_app, has_app_context

from app.utils.domain import domains_match, normalize_domain

logger = logging.getLogger("app.dataforseo")

BASE_URL = "https://api.dataforseo.com"
SEARCH_VOLUME_PATH = "/v3/keywords_data/google_ads/search_volume/live"
KEYWORD_DIFFICULTY_PATH = "/v3/dataforseo_labs/google/bulk_keyword_difficulty/live"
SEARCH_INTENT_PATH = "/v3/dataforseo_labs/google/search_intent/live"
SERP_ADVANCED_PATH = "/v3/serp/google/organic/live/advanced"

DEFAULT_LOCATION = 2840  # United States
DEFAULT_LANGUAGE = "en"
SERP_WORKERS = 4
REQUEST_TIMEOUT = 60.0


@dataclass
class KeywordMetrics:
    search_volume: int = 0
    competitive_difficulty: int = 50
    search_intent: str = "informational"
    intent_probability: float = 0.0


@dataclass
class VisibilityResult:
    domain_visible: bool | None
    visibility_position: int | None
    visibility_status: str
    source: str | None = None


class DataForSEOError(RuntimeError):
    """Raised when a DataForSEO request fails at the HTTP or task level."""


class DataForSEOClient:
    def __init__(
        self,
        login: str | None = None,
        password: str | None = None,
        location_code: int | None = None,
        language_code: str | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        if has_app_context():
            login = login if login is not None else current_app.config.get("DATAFORSEO_LOGIN")
            password = (
                password if password is not None else current_app.config.get("DATAFORSEO_PASSWORD")
            )
            location_code = location_code or current_app.config.get(
                "DATAFORSEO_LOCATION_CODE", DEFAULT_LOCATION
            )
            language_code = language_code or current_app.config.get(
                "DATAFORSEO_LANGUAGE_CODE", DEFAULT_LANGUAGE
            )
        self.login = login or ""
        self.password = password or ""
        self.location_code = int(location_code or DEFAULT_LOCATION)
        self.language_code = language_code or DEFAULT_LANGUAGE
        self.timeout = timeout

    def require_credentials(self) -> None:
        if not self.login or not self.password:
            raise DataForSEOError(
                "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in the environment"
            )

    def _post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        self.require_credentials()
        url = f"{BASE_URL}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json=payload,
                    auth=(self.login, self.password),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise DataForSEOError(f"DataForSEO request failed: {exc}") from exc

        if response.status_code >= 400:
            raise DataForSEOError(
                f"DataForSEO HTTP {response.status_code} for {path}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DataForSEOError("DataForSEO returned non-JSON body") from exc

    def _first_task(self, body: dict[str, Any]) -> dict[str, Any] | None:
        tasks = body.get("tasks") or []
        if not tasks:
            return None
        task = tasks[0]
        status = task.get("status_code")
        if status not in (20000, 20100):
            logger.warning(
                "dataforseo.task_error status=%s message=%s",
                status,
                task.get("status_message"),
            )
        return task

    def fetch_search_volume(self, keywords: list[str]) -> dict[str, int]:
        if not keywords:
            return {}
        payload = [
            {
                "keywords": keywords,
                "location_code": self.location_code,
                "language_code": self.language_code,
            }
        ]
        body = self._post(SEARCH_VOLUME_PATH, payload)
        task = self._first_task(body)
        results: dict[str, int] = {}
        for item in (task or {}).get("result") or []:
            keyword = (item.get("keyword") or "").strip().lower()
            volume = item.get("search_volume")
            if keyword:
                results[keyword] = int(volume or 0)
        return results

    def fetch_keyword_difficulty(self, keywords: list[str]) -> dict[str, int]:
        if not keywords:
            return {}
        payload = [
            {
                "keywords": keywords,
                "location_code": self.location_code,
                "language_code": self.language_code,
            }
        ]
        body = self._post(KEYWORD_DIFFICULTY_PATH, payload)
        task = self._first_task(body)
        results: dict[str, int] = {}
        for group in (task or {}).get("result") or []:
            for item in group.get("items") or []:
                keyword = (item.get("keyword") or "").strip().lower()
                difficulty = item.get("keyword_difficulty")
                if keyword and difficulty is not None:
                    results[keyword] = int(max(0, min(100, difficulty)))
        return results

    def fetch_search_intent(self, keywords: list[str]) -> dict[str, tuple[str, float]]:
        if not keywords:
            return {}
        payload = [
            {
                "keywords": keywords,
                "language_code": self.language_code,
            }
        ]
        body = self._post(SEARCH_INTENT_PATH, payload)
        task = self._first_task(body)
        results: dict[str, tuple[str, float]] = {}
        for group in (task or {}).get("result") or []:
            for item in group.get("items") or []:
                keyword = (item.get("keyword") or "").strip().lower()
                intent = item.get("keyword_intent") or {}
                label = (intent.get("label") or "informational").lower()
                probability = float(intent.get("probability") or 0.0)
                if keyword:
                    results[keyword] = (label, probability)
        return results

    def fetch_keyword_metrics(self, keywords: list[str]) -> dict[str, KeywordMetrics]:
        unique = []
        seen: set[str] = set()
        for keyword in keywords:
            key = (keyword or "").strip()
            if not key:
                continue
            lowered = key.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(key)

        volumes: dict[str, int] = {}
        difficulties: dict[str, int] = {}
        intents: dict[str, tuple[str, float]] = {}

        try:
            volumes = self.fetch_search_volume(unique)
        except DataForSEOError:
            logger.exception("dataforseo.search_volume_failed")

        try:
            difficulties = self.fetch_keyword_difficulty(unique)
        except DataForSEOError:
            logger.exception("dataforseo.keyword_difficulty_failed")

        try:
            intents = self.fetch_search_intent(unique)
        except DataForSEOError:
            logger.exception("dataforseo.search_intent_failed")

        metrics: dict[str, KeywordMetrics] = {}
        for keyword in unique:
            key = keyword.lower()
            intent_label, intent_prob = intents.get(key, ("informational", 0.0))
            metrics[key] = KeywordMetrics(
                search_volume=volumes.get(key, 0),
                competitive_difficulty=difficulties.get(key, 50),
                search_intent=intent_label,
                intent_probability=intent_prob,
            )
        return metrics

    def check_visibility(
        self,
        query_text: str,
        domain: str,
        brand_name: str | None = None,
    ) -> VisibilityResult:
        payload = [
            {
                "keyword": query_text,
                "location_code": self.location_code,
                "language_code": self.language_code,
                "depth": 10,
            }
        ]
        try:
            body = self._post(SERP_ADVANCED_PATH, payload)
        except DataForSEOError:
            logger.exception("dataforseo.serp_failed query=%s", query_text)
            return VisibilityResult(
                domain_visible=None,
                visibility_position=None,
                visibility_status="unknown",
            )

        task = self._first_task(body)
        result_items = []
        for result in (task or {}).get("result") or []:
            result_items.extend(result.get("items") or [])

        if not result_items and not (task or {}).get("result"):
            return VisibilityResult(
                domain_visible=None,
                visibility_position=None,
                visibility_status="unknown",
            )

        target = normalize_domain(domain)
        brand = (brand_name or "").strip().lower()
        organic_position: int | None = None
        ai_position: int | None = None
        mentioned_in_overview = False

        for item in result_items:
            item_type = item.get("type")
            if item_type == "organic":
                item_domain = item.get("domain") or ""
                if item_domain and domains_match(item_domain, target):
                    rank = item.get("rank_group") or item.get("rank_absolute")
                    if rank is not None:
                        organic_position = int(rank)
            elif item_type == "ai_overview":
                overview_text = " ".join(
                    filter(
                        None,
                        [
                            item.get("markdown"),
                            item.get("title"),
                            item.get("text"),
                        ],
                    )
                ).lower()
                if brand and brand in overview_text:
                    mentioned_in_overview = True
                if target in overview_text:
                    mentioned_in_overview = True
                for idx, reference in enumerate(item.get("references") or [], start=1):
                    ref_domain = reference.get("domain") or ""
                    if ref_domain and domains_match(ref_domain, target):
                        ai_position = idx
                        break
                    ref_url = reference.get("url") or ""
                    if ref_url and target in ref_url.lower():
                        ai_position = idx
                        break

        if organic_position is not None:
            return VisibilityResult(
                domain_visible=True,
                visibility_position=organic_position,
                visibility_status="visible",
                source="organic",
            )
        if ai_position is not None or mentioned_in_overview:
            return VisibilityResult(
                domain_visible=True,
                visibility_position=ai_position,
                visibility_status="visible",
                source="ai_overview",
            )
        return VisibilityResult(
            domain_visible=False,
            visibility_position=None,
            visibility_status="not_visible",
        )

    def check_visibility_batch(
        self,
        queries: list[str],
        domain: str,
        brand_name: str | None = None,
        max_workers: int = SERP_WORKERS,
    ) -> list[VisibilityResult]:
        if not queries:
            return []
        results: list[VisibilityResult | None] = [None] * len(queries)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.check_visibility, query, domain, brand_name): index
                for index, query in enumerate(queries)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception:
                    logger.exception("dataforseo.serp_worker_failed index=%s", index)
                    results[index] = VisibilityResult(
                        domain_visible=None,
                        visibility_position=None,
                        visibility_status="unknown",
                    )
        return [
            item
            if item is not None
            else VisibilityResult(None, None, "unknown")
            for item in results
        ]
