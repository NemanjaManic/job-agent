# job-agent

A personal agent that searches for **Junior AI/ML Engineer** positions and internships every day, scores relevance with an LLM, and sends a daily digest to Telegram — no manual job-board browsing required.

## How it works

```
RemoteOK + WeWorkRemotely + HelloWorld.rs + Infostud → dedup (data/seen.jsonl) → Layer 1: keyword filter → Layer 2: LLM scoring → Telegram digest
```

1. **Fetch** — each source is an independent adapter in `agent/sources/` (RemoteOK API, WeWorkRemotely RSS, HelloWorld.rs and Infostud scraping — both target the site's own AI/ML tag and internship section instead of the generic listing). `main.py` calls all of them and merges the results; if one source breaks (e.g. a site changes its HTML), the others keep working normally (`fetch_all_jobs` in `main.py`).
2. **Dedup** — every job gets two keys (source+URL, and a normalized company+title+location); already-seen ones are skipped (`agent/dedup.py`).
3. **Layer 1 (keyword filter)** — a broad, deliberately shallow filter on title/tags (`agent/filters.py`, keywords in `config.yaml`). The goal is to not miss anything relevant, not to be precise.
4. **Layer 2 (LLM scoring)** — every job that passes Layer 1 goes to Google Gemini (`agent/llm.py`), which returns a 0–10 score and a one-sentence reason against the target roles in `config.yaml`. Below the threshold (`llm.score_threshold`) it's discarded — this is where noise like "Junior Payroll Assistant" or "Data Entry Clerk" that Layer 1 wrongly let through gets cut.
5. **Delivery** — whatever passes both layers is sent as a Telegram digest, sorted by relevance (`agent/telegram.py`, `agent/format.py`).

Runs automatically every day via GitHub Actions (`.github/workflows/daily.yml`), which also commits the updated `data/seen.jsonl` back to the repo.

## Status

- ✅ Phase 1 — RemoteOK + Telegram (live)
- ✅ Phase 2 — LLM relevance ranking (Gemini, live)
- ✅ Phase 2b — additional sources: WeWorkRemotely (RSS), HelloWorld.rs and Infostud (both AI/ML tag + internships, scraping) — live
- ⬜ Phase 3 — LinkedIn/Indeed (job alert emails), email fallback

Full plan, architecture decisions and risks: [`PLAN.md`](./PLAN.md).

## Setup

Required variables (locally in `.env`, in production in the GitHub repo → Settings → Secrets and variables → Actions):

| Variable | What it's for | Where to get it |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Sending digest messages | [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_CHAT_ID` | Who it's sent to | `https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging the bot once |
| `GEMINI_API_KEY` | Layer 2 relevance scoring | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — free tier, no card needed |

```bash
cp .env.example .env   # then fill in the values
pip install -r requirements.txt
```

## Running locally

```bash
python main.py --dry-run   # does everything, just logs the digest — sends nothing
python main.py --send      # forces a real send regardless of config.yaml
python main.py             # uses run.dry_run from config.yaml
```

## Configuration

Everything that changes often (target roles, keywords, LLM score threshold, sources) lives in [`config.yaml`](./config.yaml) — no need to touch code to change the agent's behavior.

## Structure

```
main.py                        orchestration: fetch → dedup → filter → LLM → send → state
config.yaml                    all settings (no code)
agent/
  config.py                    loads config.yaml and env credentials
  dedup.py                     dedup keys + reading/writing data/seen.jsonl
  filters.py                   Layer 1 — keyword filter
  llm.py                       Layer 2 — relevance scoring via the Gemini API (with rate-limit retry)
  format.py                    Telegram message formatting
  telegram.py                  sending via the Telegram Bot API
  sources/
    remoteok.py                 RemoteOK API adapter
    weworkremotely.py           WeWorkRemotely RSS adapter
    helloworld.py                HelloWorld.rs adapter (AI/ML tag + internships, scraping)
    infostud.py                  Infostud adapter (AI/ML tag + internships, __NEXT_DATA__ JSON)
data/seen.jsonl                dedup state, append-only, auto-committed by GitHub Actions
.github/workflows/daily.yml    daily cron + workflow_dispatch for manual runs
```

## Known limitations

- GitHub Actions' `schedule` trigger isn't guaranteed to be on time — the cron is set for 05:17 UTC, but in practice it can run hours late (free tier, common for low-activity repos). Not a bug in the code; if it's an issue, the fix is an external pinger (e.g. cron-job.org) that triggers `workflow_dispatch` at the exact time.
- The Gemini free tier has a limit of **15 requests/minute**. `agent/llm.py` automatically waits and retries when the limit is hit (Google itself specifies how many seconds to wait), so a run just takes a bit longer that day instead of crashing.
