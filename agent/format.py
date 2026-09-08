from __future__ import annotations

from datetime import datetime, timezone


def _age_str(posted_date: str | None) -> str:
    if not posted_date:
        return "datum nepoznat"
    try:
        posted = datetime.fromisoformat(posted_date.replace("Z", "+00:00"))
    except ValueError:
        return "datum nepoznat"
    days = (datetime.now(timezone.utc) - posted).days
    if days <= 0:
        return "danas"
    if days == 1:
        return "pre 1 dan"
    return f"pre {days} dana"


def format_job(job: dict) -> str:
    age = _age_str(job.get("posted_date"))
    return (
        f"🔹 <b>{job['title']}</b> — {job['company']}\n"
        f"📍 {job['location']}  ·  🕒 {age}  ·  {job['source']}\n"
        f"🔗 {job['url']}"
    )


def format_digest(jobs: list[dict]) -> str:
    return "\n\n".join(format_job(job) for job in jobs)
