from __future__ import annotations

import json
import re
import time

import httpx

MODEL = "gemini-flash-lite-latest"  # alias na najnoviji/najjeftiniji flash model — ne pinuje verziju koja može biti povučena
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

# Besplatan tier ima limit od 15 zahteva/minut (izmereno — vidi grešku ispod).
# Google u 429 telu poruke sam kaže koliko tačno da se sačeka pre ponovnog pokušaja.
MAX_RETRIES = 5
DEFAULT_RETRY_SECONDS = 20.0
_RETRY_DELAY_PATTERN = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)

SYSTEM_PROMPT = (
    "Ti si filter za oglase za posao. Korisnik traži isključivo junior/intern pozicije u "
    "oblasti AI, machine learning ili data (vidi ciljane pozicije ispod) — NE senior/mid "
    "pozicije, i NE nepovezane uloge koje samo slučajno pominju reč 'AI' ili 'data' u "
    "naslovu/tagovima (npr. marketing, HR, customer support, data entry, payroll, prodaja).\n\n"
    "Oceni dati oglas brojem 0-10:\n"
    "0-2 = potpuno nepovezano, lažni pogodak na keyword\n"
    "3-5 = tehnička uloga ali ne AI/ML/data, ili jeste AI/ML ali jasno senior/mid nivo\n"
    "6-8 = junior/intern AI, ML ili data pozicija, dovoljno blizu da vredi pogledati\n"
    "9-10 = tačan pogodak: junior/intern AI ili ML engineer/analyst pozicija ili praksa"
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "score": {"type": "INTEGER", "description": "Ocena relevantnosti 0-10."},
        "reason": {"type": "STRING", "description": "Jedna kratka rečenica na srpskom — zašto ova ocena."},
    },
    "required": ["score", "reason"],
}


def score_job(job: dict, target_roles: list[str], api_key: str) -> tuple[int, str]:
    user_content = (
        f"Ciljane pozicije korisnika: {', '.join(target_roles)}\n\n"
        f"Oglas za ocenu:\n"
        f"Naslov: {job.get('title', '')}\n"
        f"Kompanija: {job.get('company', '')}\n"
        f"Tagovi: {', '.join(job.get('tags', []))}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
        },
    }

    for attempt in range(MAX_RETRIES):
        response = httpx.post(
            API_URL,
            headers={"x-goog-api-key": api_key, "content-type": "application/json"},
            json=payload,
            timeout=30,
        )
        if response.status_code == 429 and attempt < MAX_RETRIES - 1:
            time.sleep(_retry_delay_seconds(response.text))
            continue
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        return int(result["score"]), str(result["reason"])

    raise RuntimeError("Gemini API i dalje vraća 429 posle svih pokušaja.")


def _retry_delay_seconds(error_body: str) -> float:
    match = _RETRY_DELAY_PATTERN.search(error_body)
    if match:
        return float(match.group(1)) + 1  # mala margina
    return DEFAULT_RETRY_SECONDS
