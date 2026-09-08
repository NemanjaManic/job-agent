from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    # Windows konzola ume da bude cp1252 umesto UTF-8 — bez ovoga se emoji/č/ž lome u logu.
    # logging pise na stderr po default-u, pa mora i taj stream da se prekonfigurise.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

from agent.config import load_config, telegram_credentials
from agent.dedup import append_records, load_seen, logical_key, source_key
from agent.filters import matches_layer1
from agent.format import format_digest
from agent.sources import remoteok
from agent.telegram import send_digest

DATA_PATH = Path(__file__).resolve().parent / "data" / "seen.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("job-agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Ne šalje Telegram poruku, samo ispisuje digest u log."
    )
    parser.add_argument(
        "--send", action="store_true", help="Forsira stvarno slanje, čak i ako je run.dry_run: true u config.yaml."
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    config = load_config()

    if args.send:
        dry_run = False
    elif args.dry_run:
        dry_run = True
    else:
        dry_run = config["run"]["dry_run"]

    seen_source_keys, seen_logical_keys = load_seen(DATA_PATH)

    raw_jobs = remoteok.fetch()
    log.info("RemoteOK: %d oglasa dohvaćeno", len(raw_jobs))

    positive_keywords = config["filters"]["positive_keywords"]
    new_records: list[dict] = []
    to_send: list[dict] = []

    for job in raw_jobs:
        s_key = source_key(job["source"], job["url"])
        l_key = logical_key(job["company"], job["title"], job["location"])
        if s_key in seen_source_keys or l_key in seen_logical_keys:
            continue

        seen_source_keys.add(s_key)
        seen_logical_keys.add(l_key)

        matched = matches_layer1(job, positive_keywords)
        record = {
            **job,
            "source_key": s_key,
            "logical_key": l_key,
            "first_seen_at": datetime.now(timezone.utc).isoformat(),
            "llm_score": None,
            "llm_reason": None,
            "status": "filtered_keyword",
            "sent_at": None,
        }
        if matched:
            to_send.append(job)
            record["status"] = "sent_dry_run" if dry_run else "sent"
        new_records.append(record)

    log.info("Novih oglasa: %d, prolazi Sloj 1 filter: %d", len(new_records), len(to_send))

    if to_send:
        digest = format_digest(to_send)
        if dry_run:
            log.info("DRY RUN — digest koji bi bio poslat:\n%s", digest)
        else:
            token, chat_id = telegram_credentials()
            if not token or not chat_id:
                raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nisu podešeni (env ili GitHub Secrets).")
            send_digest(token, chat_id, digest)
            sent_at = datetime.now(timezone.utc).isoformat()
            for record in new_records:
                if record["status"] == "sent":
                    record["sent_at"] = sent_at
    else:
        log.info("Nema novih oglasa koji prolaze filter — ništa se ne šalje.")

    append_records(DATA_PATH, new_records)


if __name__ == "__main__":
    run()
