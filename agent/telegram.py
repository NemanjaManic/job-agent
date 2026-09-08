from __future__ import annotations

import httpx

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 3500  # margina ispod Telegram limita od 4096 karaktera po poruci


def _chunks(text: str) -> list[str]:
    blocks = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > MAX_LEN and current:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_digest(token: str, chat_id: str, text: str) -> None:
    url = API_URL.format(token=token)
    for chunk in _chunks(text):
        response = httpx.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
