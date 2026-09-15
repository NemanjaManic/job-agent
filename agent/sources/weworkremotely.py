from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

RSS_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
SOURCE = "weworkremotely"
HEADERS = {"User-Agent": "job-agent/0.1 (personal daily digest, non-commercial)"}


def fetch() -> list[dict]:
    response = httpx.get(RSS_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    return [_normalize(item) for item in root.iter("item")]


def _normalize(item: ElementTree.Element) -> dict:
    # Naslov je u formatu "Kompanija: Pozicija" — ako nema separatora, tretiramo ceo tekst kao naziv pozicije.
    raw_title = (item.findtext("title") or "").strip()
    company, sep, title = raw_title.partition(": ")
    if not sep:
        company, title = "", company

    url = (item.findtext("link") or item.findtext("guid") or "").strip()
    region = (item.findtext("region") or "").strip()
    category = (item.findtext("category") or "").strip()

    return {
        "source": SOURCE,
        "title": title.strip(),
        "company": company.strip(),
        "location": region or "Remote",
        "url": url,
        "posted_date": _parse_date(item.findtext("pubDate")),
        "tags": [category] if category else [],
    }


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None
