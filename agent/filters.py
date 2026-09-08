from __future__ import annotations

import re


def matches_layer1(job: dict, positive_keywords: list[str]) -> bool:
    """Široki filter (PLAN.md sekcija 3.1): propušta sve što je iole blizu.
    Precizno rangiranje dolazi tek u Fazi 2 (LLM), namerno se ne dodaje ovde.

    Poređenje je po celim rečima (\\b), ne po podstringu — bez toga npr. "AI"
    lažno pogađa "Maintenance", "Detailer", "Mail", "Captain", "Airport"."""
    haystack = " ".join([job.get("title", ""), " ".join(job.get("tags", []))])
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", haystack, re.IGNORECASE)
        for keyword in positive_keywords
    )
