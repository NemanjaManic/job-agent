from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

SOURCE = "helloworld"
BASE_URL = "https://www.helloworld.rs"
# Dva ciljana lista — ne generička /oglasi-za-posao (previše šuma) — vidi PLAN.md sekcija 5:
# "Najbolji lokalni izvor zbog ugrađenog junior/praksa filtera — lakše targetirati nego generičku listu".
LISTING_URLS = [
    f"{BASE_URL}/oglasi-za-posao/aiml",  # sajtov ugrađen AI/ML tag filter
    f"{BASE_URL}/prakse",  # sajtova dedikovana "Prakse" (internship) sekcija
]
HEADERS = {"User-Agent": "job-agent/0.1 (personal daily digest, non-commercial)"}


def fetch() -> list[dict]:
    jobs: list[dict] = []
    for url in LISTING_URLS:
        response = httpx.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        jobs.extend(_parse_listing(response.text))
    return jobs


def _parse_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    for title_a in soup.select("a.__ga4_job_title[data-job-id]"):
        job_id = title_a["data-job-id"]
        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        url = url.split("?")[0]  # ukloni tracking query parametre (cat, page, item_index...)

        # Kompanijin <a> ponekad nema klasu __ga4_job_company (npr. kad nema strane kompanije) —
        # osloni se na strukturu (h4 odmah posle h3 sa naslovom), ne na klasu.
        company = ""
        h3 = title_a.find_parent("h3")
        if h3:
            h4 = h3.find_next_sibling("h4")
            if h4:
                company_a = h4.find("a")
                if company_a:
                    company = company_a.get_text(strip=True)

        card = _find_card(title_a)
        location = _extract_location(card) if card else ""
        seniority = _extract_seniority(card, job_id) if card else ""

        tags = [seniority] if seniority else []
        jobs.append(
            {
                "source": SOURCE,
                "title": title,
                "company": company,
                "location": location or "Srbija",
                "url": url,
                # Sajt prikazuje rok za prijavu, ne datum objave — ne mešati ta dva (vidi napomenu ispod).
                "posted_date": None,
                "tags": tags,
            }
        )
    return jobs


def _find_card(title_a):
    """Popne se od naslova do zajedničkog kontejnera oglasa (identifikovan po tome
    da sadrži ikonicu lokacije), jer omotač div-ovi nemaju stabilnu klasu/ID."""
    node = title_a
    for _ in range(12):
        node = node.parent
        if node is None:
            return None
        if node.select_one("i.la-map-marker"):
            return node
    return None


def _extract_location(card) -> str:
    icon = card.select_one("i.la-map-marker")
    if not icon:
        return ""
    p = icon.find_next("p")
    return p.get_text(strip=True) if p else ""


def _extract_seniority(card, job_id: str) -> str:
    badge = card.select_one(f'.__ga4_job_seniority[data-job-id="{job_id}"]')
    return badge.get_text(strip=True) if badge else ""
