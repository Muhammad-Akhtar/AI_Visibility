"""Agent 1 — Query Discovery.

Generates 12–15 commercially relevant questions a buyer would ask an AI
assistant in the profile's competitive space.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas import DiscoveredQueryItem, DiscoveryOutput

SYSTEM_PROMPT = """You are a senior generative-engine-optimization (GEO) researcher.

Your job is to invent the questions that real buyers type into ChatGPT, Claude,
Perplexity, and Google AI Overviews when they are evaluating products in a
given market.

Constraints:
- Return BETWEEN 12 and 15 questions. Never fewer than 10, never more than 20.
- Questions must be natural spoken/typed English, the way a human asks an AI
  assistant — not keyword-stuffed search strings.
- Mix these commercially valuable intents:
  1. "best of" / category roundups
  2. head-to-head comparisons (target brand vs a named competitor)
  3. "how to" workflows the product helps with
  4. pricing / ROI / "is it worth it"
  5. alternative / "instead of" questions
- Every question must be relevant to the given industry and plausible for a
  buyer in that space. Do not invent unrelated verticals.
- Include the target brand in SOME (not all) questions; leave others generic
  so we can measure whether the brand appears unprompted.
- seed_keyword must be a Google Ads-safe phrase: lowercase, at most 10 words,
  at most 80 characters, no punctuation except spaces and hyphens. It should
  be the core commercial keyword behind the question (e.g. question
  "What is the best SEO content tool?" → seed_keyword "best seo content tool").

Return ONLY valid JSON matching this schema exactly:
{
  "queries": [
    {
      "query_text": "string, the full natural-language question",
      "seed_keyword": "string, 2-10 word keyword phrase",
      "intent_hint": "commercial" | "transactional" | "informational" | "navigational"
    }
  ]
}

Do not wrap the JSON in markdown. Do not add keys that are not in the schema.
"""


class QueryDiscoveryAgent(BaseAgent):
    name = "query_discovery"
    temperature = 0.5

    def discover(self, profile: dict, run_uuid: str = "-") -> list[DiscoveredQueryItem]:
        competitors = profile.get("competitors") or []
        competitor_list = ", ".join(competitors) if competitors else "(none provided)"
        user_prompt = (
            "Generate commercially relevant AI-assistant questions for this business.\n\n"
            f"Brand name: {profile['name']}\n"
            f"Domain: {profile['domain']}\n"
            f"Industry: {profile['industry']}\n"
            f"Description: {profile['description']}\n"
            f"Competitors: {competitor_list}\n"
        )
        output = self.complete_json(
            SYSTEM_PROMPT, user_prompt, DiscoveryOutput, run_uuid=run_uuid
        )
        queries = output.queries[:20]
        seen: set[str] = set()
        unique: list[DiscoveredQueryItem] = []
        for item in queries:
            key = item.query_text.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique
