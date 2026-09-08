from __future__ import annotations

import httpx

API_URL = "https://remoteok.com/api"
SOURCE = "remoteok"

# RemoteOK ToS: ako se rezultati ikad javno prikažu (npr. Faza 5 dashboard),
# obavezan je backlink ka RemoteOK. Za privatan Telegram digest nije relevantno.
HEADERS = {"User-Agent": "job-agent/0.1 (personal daily digest, non-commercial)"}


def fetch() -> list[dict]:
    response = httpx.get(API_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    return [_normalize(job) for job in data if job.get("id")]


def _normalize(job: dict) -> dict:
    job_id = job.get("id", "")
    slug = job.get("slug", "")
    url = job.get("url") or f"https://remoteok.com/remote-jobs/{job_id}-{slug}"
    return {
        "source": SOURCE,
        "title": (job.get("position") or "").strip(),
        "company": (job.get("company") or "").strip(),
        "location": job.get("location") or "Remote",
        "url": url,
        "posted_date": job.get("date"),
        "tags": job.get("tags", []),
    }
