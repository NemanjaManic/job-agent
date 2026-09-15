from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx

SOURCE = "infostud"
BASE_URL = "https://poslovi.infostud.com/oglasi-za-posao-it/beograd"
# Dva ciljana taga (isti brojevi ID-jevi kao HelloWorld.rs — zajednička Infostud/HelloWorld
# taksonomija, iste kompanije) — ne generička IT/Beograd lista (111 oglasa, nizak junior/AI
# signal, vidi PLAN.md sekcija 5).
LISTING_URLS = [
    f"{BASE_URL}?tags=563",  # AI/ML
    f"{BASE_URL}?tags=340",  # Prakse
]
HEADERS = {"User-Agent": "job-agent/0.1 (personal daily digest, non-commercial)"}
_NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def fetch() -> list[dict]:
    jobs: list[dict] = []
    for url in LISTING_URLS:
        response = httpx.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        jobs.extend(_parse_listing(response.text))
    return jobs


def _parse_listing(html: str) -> list[dict]:
    # Next.js sajt — podaci su u __NEXT_DATA__ JSON blobu, pouzdanije od HTML selektora.
    match = _NEXT_DATA_PATTERN.search(html)
    if not match:
        return []
    data = json.loads(match.group(1))
    raw_jobs = data["props"]["pageProps"]["initialSearchResults"]["jobs"]["primary"]
    return [_normalize(job) for job in raw_jobs]


def _normalize(job: dict) -> dict:
    return {
        "source": SOURCE,
        "title": (job.get("title") or "").strip(),
        "company": (job.get("companyName") or "").strip(),
        "location": job.get("location") or "Srbija",
        "url": job.get("url", ""),
        "posted_date": _parse_date(job.get("onlineViewDate")),
        "tags": job.get("itTags") or [],
    }


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d.%m.%Y").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None
