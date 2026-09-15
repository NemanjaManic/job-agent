from __future__ import annotations

import json

import httpx

MODEL = "gemini-flash-lite-latest"  # alias na najnoviji/najjeftiniji flash model — ne pinuje verziju koja može biti povučena
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

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
    response = httpx.post(
        API_URL,
        headers={"x-goog-api-key": api_key, "content-type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_content}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(text)
    return int(result["score"]), str(result["reason"])
