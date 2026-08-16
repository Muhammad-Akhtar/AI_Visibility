"""Agent 3 — Content Recommendation.

Given the highest-opportunity queries where the target domain is NOT
visible, produce 3–5 specific pieces of content to create.
"""

from __future__ import annotations

from app.agents.base import AgentOutputError, BaseAgent
from app.agents.scoring import ScoredQuery
from app.schemas import RecommendationItem, RecommendationOutput

SYSTEM_PROMPT = """You are a content strategist who specialises in AI search
visibility (GEO) and classic SEO.

You receive a business profile and a ranked list of high-opportunity queries
where the brand currently does NOT appear in AI-generated answers or Google
AI Overviews. Your job is to recommend 3 to 5 specific pieces of content that
would make an AI assistant more likely to cite or mention the brand for those
queries.

Rules:
- Produce 3, 4, or 5 recommendations. Never fewer than 3 if at least 3 gap
  queries are provided. Never more than 5.
- Each recommendation must map to ONE gap query via target_query_index
  (0-based index into the Gap queries array you are given) AND repeat the
  query text in target_query_text.
- Be specific: name the page, the angle, and the sections to cover. Vague
  advice such as "write a blog about SEO" is not acceptable.
- Prefer comparison pages and "best of" roundups for commercial queries,
  how-to guides / FAQs for informational queries, and pricing or use-case
  landing pages for transactional queries.
- Rationale must explain WHY this content closes the visibility gap for that
  query (what an AI assistant would cite).
- target_keywords: 3–7 phrases the page should rank for / be cited for.
- priority: "high" for the strongest commercial/comparison gaps, otherwise
  "medium" or "low".

Return ONLY valid JSON matching this schema exactly:
{
  "recommendations": [
    {
      "target_query_index": 0,
      "target_query_text": "the full query string",
      "content_type": "blog_post" | "landing_page" | "faq" | "comparison_guide" | "case_study",
      "title": "suggested page title",
      "rationale": "2–4 sentences explaining why this closes the gap",
      "target_keywords": ["keyword one", "keyword two"],
      "priority": "high" | "medium" | "low"
    }
  ]
}

Do not wrap the JSON in markdown. Do not add keys that are not in the schema.
"""


class ContentRecommendationAgent(BaseAgent):
    name = "content_recommendation"
    temperature = 0.4

    def recommend(
        self,
        profile: dict,
        gap_queries: list[ScoredQuery],
        run_uuid: str = "-",
    ) -> list[RecommendationItem]:
        if not gap_queries:
            return []

        gap_block = []
        for index, query in enumerate(gap_queries):
            gap_block.append(
                f"{index}. query={query.query_text!r} "
                f"volume={query.estimated_search_volume} "
                f"difficulty={query.competitive_difficulty} "
                f"intent={query.search_intent} "
                f"opportunity={query.opportunity_score:.3f}"
            )
        competitors = ", ".join(profile.get("competitors") or []) or "(none provided)"
        user_prompt = (
            "Recommend content that would help this brand appear in AI answers "
            "for the gap queries below.\n\n"
            f"Brand name: {profile['name']}\n"
            f"Domain: {profile['domain']}\n"
            f"Industry: {profile['industry']}\n"
            f"Description: {profile['description']}\n"
            f"Competitors: {competitors}\n\n"
            "Gap queries (0-based index):\n"
            + "\n".join(gap_block)
        )
        try:
            output = self.complete_json(
                SYSTEM_PROMPT, user_prompt, RecommendationOutput, run_uuid=run_uuid
            )
        except AgentOutputError:
            return []

        valid: list[RecommendationItem] = []
        for item in output.recommendations[:5]:
            if item.target_query_index >= len(gap_queries) and not item.target_query_text:
                continue
            valid.append(item)
        return valid
