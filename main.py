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

from agent.config import gemini_credentials, load_config, telegram_credentials
from agent.dedup import append_records, load_seen, logical_key, source_key
from agent.filters import matches_layer1
from agent.format import format_digest
from agent.llm import score_job
from agent.sources import helloworld, infostud, remoteok, weworkremotely
from agent.telegram import send_digest

DATA_PATH = Path(__file__).resolve().parent / "data" / "seen.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("job-agent")

# Mapiranje source id (config.yaml sources.enabled) -> adapter modul.
# Izvori bez implementiranog adaptera (Faza 3+) se tiho preskaču dok ne budu spremni.
SOURCE_ADAPTERS = {
    "remoteok": remoteok,
    "weworkremotely": weworkremotely,
    "helloworld_rs": helloworld,
    "infostud_it_beograd": infostud,
}


def fetch_all_jobs(config: dict) -> list[dict]:
    jobs: list[dict] = []
    for source_cfg in config["sources"]["enabled"]:
        source_id = source_cfg["id"]
        adapter = SOURCE_ADAPTERS.get(source_id)
        if adapter is None:
            continue
        try:
            source_jobs = adapter.fetch()
        except Exception:
            log.exception("%s: fetch nije uspeo, preskačem izvor za danas.", source_id)
            continue
        log.info("%s: %d oglasa dohvaćeno", source_id, len(source_jobs))
        jobs.extend(source_jobs)
    return jobs


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

    raw_jobs = fetch_all_jobs(config)
    log.info("Ukupno dohvaćeno svih izvora: %d", len(raw_jobs))

    positive_keywords = config["filters"]["positive_keywords"]
    new_records: list[dict] = []
    layer1_passed: list[dict] = []

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
            record["status"] = "sent_dry_run" if dry_run else "sent"
            layer1_passed.append(record)
        new_records.append(record)

    log.info("Novih oglasa: %d, prolazi Sloj 1 filter: %d", len(new_records), len(layer1_passed))

    to_send: list[dict] = layer1_passed

    if config["llm"]["enabled"] and layer1_passed:
        api_key = gemini_credentials()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY nije podešen (env ili GitHub Secrets).")

        target_roles = config["profile"]["target_roles"]
        threshold = config["llm"]["score_threshold"]
        max_calls = config["llm"].get("max_calls_per_run", 50)

        scorable = layer1_passed[:max_calls]
        if len(layer1_passed) > max_calls:
            log.warning(
                "Sloj 1 je propustio %d oglasa, LLM ocenjuje samo prvih %d (max_calls_per_run) radi kontrole troška.",
                len(layer1_passed),
                max_calls,
            )

        for record in scorable:
            score, reason = score_job(record, target_roles, api_key)
            record["llm_score"] = score
            record["llm_reason"] = reason
            if score < threshold:
                record["status"] = "filtered_llm"

        to_send = sorted(
            (r for r in layer1_passed if r["status"] in ("sent", "sent_dry_run")),
            key=lambda r: r["llm_score"] or 0,
            reverse=True,
        )
        log.info("LLM: %d ocenjeno, %d iznad praga (%d)", len(scorable), len(to_send), threshold)

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
            for record in to_send:
                record["sent_at"] = sent_at
    else:
        log.info("Nema novih oglasa koji prolaze filter — ništa se ne šalje.")

    append_records(DATA_PATH, new_records)


if __name__ == "__main__":
    run()
