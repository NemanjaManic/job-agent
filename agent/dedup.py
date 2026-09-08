from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Uklanja česte sufikse (m/ž, remote, hybrid...) pre poređenja da isti oglas
# sa dva izvora ne prođe kao "različit" zbog kozmetičke razlike u naslovu.
_SUFFIX_PATTERN = re.compile(r"\((?:m/ž|m/f|f/m|remote|hybrid)\)", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    text = text.lower()
    text = _SUFFIX_PATTERN.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def source_key(source: str, url: str) -> str:
    raw = f"{source}:{url.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def logical_key(company: str, title: str, location: str) -> str:
    raw = "|".join(_normalize(x) for x in (company, title, location))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_seen(path: Path) -> tuple[set[str], set[str]]:
    source_keys: set[str] = set()
    logical_keys: set[str] = set()
    if not path.exists():
        return source_keys, logical_keys
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            source_keys.add(record["source_key"])
            logical_keys.add(record["logical_key"])
    return source_keys, logical_keys


def append_records(path: Path, records: list[dict]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
