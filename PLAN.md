# Plan: AI job-search agent (Junior AI/ML Engineer + internships)

Focus: **Junior AI Engineer / Junior ML Engineer / internships**, location **Serbia + foreign remote**, hosted on **GitHub Actions**.

**Core assumption shaping the whole design:** for this profile in Serbia, realistically expect **0–3 new relevant postings a day**, with days having none at all. That means the problem isn't *volume* but *finding the relevant signal in the noise* — hence the "broad filter + LLM judgment" strategy, not a "narrow keyword filter". This assumption was checked in Phase 0.5 before any real code was written.

---

## 0. Working rule: who commits and pushes to GitHub

**All `git commit` and `git push` operations during development are done exclusively by the user. Claude Code (the assistant) never runs those commands itself.**

Specifically:
- **Repo creation (Phase 0):** the user creates the GitHub repo themselves (via github.com or `gh repo create`) and does the initial commit/push. The assistant may prepare/write files locally (code, `config.yaml`, workflow YAML), but does not run `git init`, `git commit`, `git push`, or any other command that changes git history or the remote — even with prior approval for a similar action earlier in the session.
- **Throughout the project:** every code change the assistant makes stays as a local, uncommitted change until the user personally reviews and commits/pushes it.
- **Exception — automatic state commit in production (Phase 1+):** once the agent is deployed, the GitHub Actions workflow (`github-actions[bot]`) commits and pushes the updated `data/seen.jsonl` (dedup state) itself every day, via the built-in, repo-scoped `GITHUB_TOKEN` — this is a separate, pre-agreed mechanism (see section 6), **not** the same as the assistant pushing on the user's behalf. These commits are fully visible and clearly labeled:
  - the author is `github-actions[bot]` (a distinct avatar, clearly separated from the user's own account in history and blame view),
  - a normal commit message and normal diff — exactly what changed is visible,
  - the token is scoped only to that repo, with no access to the account, other repos, or repo settings beyond what's explicitly allowed in the workflow's `permissions:` block.

  **Confirmed with the user:** this automatic bot-commit mechanism is accepted and remains part of the design.

### When something is unclear — ask, don't assume
If at any stage (source selection, filter format, error behavior, message content, etc.) something isn't explicitly covered by the plan or is ambiguous, the assistant **asks the user** before making and implementing a decision — it doesn't guess or pick a "reasonable" option on its own when there's genuine uncertainty about what the user wants.

### Protecting private/sensitive data
The assistant **does not publish** (in the public repo, public GitHub Actions logs, commit messages, issue/PR descriptions, or any other publicly visible place) information that could compromise the user — including, but not limited to:
- personal data (name, email, phone, address, CV/profile from `config.yaml`),
- API keys, tokens, passwords, app passwords — these go exclusively into GitHub Secrets, never into code, a commit, a log, or a config file that gets committed,
- private email inbox contents (for IMAP parsing of job alert emails, section 3),
- anything from internal conversations/notes the user wouldn't want to be publicly visible.

The repo is already planned to be **private** (Phase 0), which is the first line of defense, but this rule applies regardless — e.g. GitHub Actions logs can leak or accidentally become public, so sensitive data isn't printed into them either (use GitHub Actions masking/secrets for anything secret).

---

## 1. Tech stack and why

| Component | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Best ecosystem for parsing/scraping (`httpx`, `feedparser`, `BeautifulSoup`/`lxml`), runs smoothly on the `ubuntu-latest` runner, no compilation |
| HTTP | `httpx` | Calls to APIs, fetching HTML/RSS pages; has built-in timeout/retry handling |
| Parsing | `feedparser` (RSS), `BeautifulSoup` (HTML fallback) | RSS is preferred where it exists — more stable than HTML scraping |
| Headless browser | **Not used** (not even Playwright) | JS-heavy sites are handled through an intermediary or skipped; a browser on the runner is slow, fragile, and a sign the source probably shouldn't be scraped |
| Dedup store | **`data/seen.jsonl`** (append-only JSON Lines), committed back to the repo | See section 4 — deliberately **not** SQLite |
| Configuration | `config.yaml` (roles, keywords, locations, sources, thresholds) | Change behavior without touching code |
| LLM ranking | **Google Gemini API** (free tier), from Phase 2 | See section 3.1 — switched from the originally planned Claude API because the user doesn't have Anthropic credits; Gemini's free tier covers this volume at no cost |
| Sending messages | Telegram Bot API + `smtplib` email fallback | See section 2 |
| Orchestration | GitHub Actions (`schedule` + `workflow_dispatch`) | See section 6 |
| Secrets | GitHub Actions Secrets | Never in code/the repo |

No Node.js, Docker, Postgres — overengineering for a personal project of this size.

---

## 2. Sending messages

### Telegram (primary channel)
1. Chat with **@BotFather** on Telegram → `/newbot` → name and username → get a **bot token**.
2. Send your bot any message (e.g. `/start`).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` → find your **chat_id** in the JSON.
4. Sending = POST to `https://api.telegram.org/bot<TOKEN>/sendMessage` with `chat_id` and `text` (supports HTML/Markdown and links).
5. Token and chat_id → GitHub Secrets.

Free, no relevant limits for one digest a day.

### Message format (✅ implemented as described)
Per job:
```
🔹 <b>Job title</b> — Company
📍 Location / Remote  ·  🕒 posted X days ago  ·  source
💡 [1 sentence: why this is relevant to you — the Layer 2 LLM reason]
🔗 link
```
**Job age is a mandatory field** — junior positions fill up fast, a posting from three weeks ago isn't worth the same as yesterday's. If the source doesn't give a date, show "date unknown" rather than omitting the line.

### Behavior when there are no new postings
**Send nothing.** At the expected volume (often 0 new per day), a daily "0 new" message trains you to ignore the bot within a week — which defeats the whole point of the project. Instead: a weekly summary on Fridays ("this week: 4 sent, 31 filtered, all sources healthy") that confirms the agent is working. *(Not yet implemented — planned for Phase 4.)*

### Email (fallback)
- Gmail SMTP + **App Password** (requires 2FA; a regular password won't work), ~500 emails/day limit — more than enough.
- Alternative: SendGrid free tier (100/day).
- Role: (a) fallback if Telegram sending fails, (b) error alerting when a run breaks.

### WhatsApp / Viber (note only, not to be implemented)
WhatsApp Cloud API requires a Meta Business account and verification, and charges past the free threshold; Twilio charges per message; Viber requires the user to manually subscribe to the bot. Telegram covers the need — this stays in Phase 5, only if a concrete reason comes up.

---

## 3. Job sources and filtering strategy

Priority: **API > RSS > careful scraping**.

### 3.1 Filtering strategy (two-layer, ✅ implemented as described)

A keyword filter alone doesn't work for this profile. Junior AI/ML positions in Serbia are often advertised as "Python Developer", "Data Analyst", "Junior Software Engineer", "ML intern" — with no AI word in the title at all. An aggressive negative-keyword list (`senior`, `5+ years`, `lead`) would eat exactly the postings you want, since postings often mention "senior" in the team description.

- **Layer 1 — broad, cheap filter (code):** lets through anything even remotely close (tech positions, junior/intern/entry signals, or the absence of a clear senior signal). The goal is *not to lose anything*, not to be precise. Expected: 20–50 postings a day pass through.
- **Layer 2 — LLM judgment (Google Gemini API, free tier):** for every posting from Layer 1, the model gets the target roles from `config.yaml` and the posting text, and returns a `score` (0–10) + one-sentence reason. Only what's above the threshold (currently 6) gets sent, sorted by score; the reason goes into the Telegram message. *(Note: by the user's explicit choice, the model does **not** get a personal CV/skills profile — only the generic target roles in `config.yaml`, for privacy reasons.)*

Cost: at this volume, Gemini's free tier (15 requests/minute) covers it at **zero cost** — this is why LLM ranking was moved from Phase 5 into Phase 2 in the original plan: it solves the project's central problem, not just cosmetics. The free-tier rate limit was hit during real testing; `agent/llm.py` handles it with automatic retry using Google's suggested wait time, so a run just takes a little longer instead of failing.

### Legal note (for all scraping sources)
- Check `robots.txt` and the ToS of every site before implementing.
- Scraping: **once a day**, a real User-Agent that identifies the bot and gives contact info, no parallel requests, no redistribution of data (you're the only recipient).
- If a site forbids scraping or starts blocking — the source is **disabled or replaced**, protections are never bypassed.

---

## 4. Dedup store

**Format: `data/seen.jsonl`** — one JSON object per line, append-only. ✅ Implemented as described.

Why not SQLite: SQLite is a binary file. Committed to git on every run, that means a full new copy in history, an unreadable diff, and an **unresolvable merge conflict**. JSONL is text → the diff shows exactly what the agent saw on which day, conflicts are resolved by hand, the repo doesn't balloon. If queries are ever needed, SQLite can be generated locally from the JSONL.

Fields per record:

| Field | Description |
|---|---|
| `source_key` | Hash of `source + normalized_url` — a posting's identity on a specific source |
| `logical_key` | Hash of normalized `company + title + location` — see below |
| `source` | e.g. `remoteok`, `infostud`, `helloworld`, `weworkremotely` |
| `title`, `company`, `location`, `url` | Basic data |
| `posted_date` | Posting date if the source provides one (nullable) |
| `first_seen_at` | When the agent first saw it |
| `llm_score`, `llm_reason` | Layer 2 result (nullable if it never reached the LLM) |
| `status` | `sent` / `sent_dry_run` / `filtered_keyword` / `filtered_llm` |
| `sent_at` | When it was sent (nullable) |

**Two keys, not one.** A hash of just `source + url` would let the same posting that appears on both RemoteOK and another board through twice — you'd get it twice. Hence `logical_key`: lowercase, punctuation stripped, suffixes like `(m/f)`, `(remote)`, `- Belgrade` stripped. A posting is new only if **both** keys are unseen.

Run flow: fetch (all sources) → normalize → compute both keys → drop already-seen → Layer 1 filter → Layer 2 (LLM) → sort by score → send → **write all new records** (sent and rejected alike, with a reason) → commit & push.

Rejected postings are kept so they aren't reprocessed tomorrow (saves LLM calls) and so you can see *why* something wasn't sent.

---

## 5. Phase 0.5 — Source recon (done, then re-verified during implementation)

"Relevant" = junior/intern AI, ML, data, or Python position, Serbia or remote open to Serbia.

Decision rule: 0–2 postings/30 days → skip; API/RSS + ≥3 → implement; scraping only + ≥5 → implement, but later (Phase 2b); robots.txt blocks exactly the search/filters → skip regardless of everything else.

> **Note on method:** the original version of this table was filled in with tools (WebFetch/WebSearch) instead of manual browsing, to save time. During actual implementation (Phase 2b), several sites turned out to have changed or to work differently than the initial recon suggested — HelloWorld.rs's URL scheme, for instance, doesn't match what the earlier automated pass found. The table below reflects what's actually implemented and verified working, not just the original probe.

| Source | Has RSS? | Has API? | robots.txt allows it? | Finding | Decision |
|---|---|---|---|---|---|
| **RemoteOK** | – | ✅ `remoteok.com/api`, no auth, confirmed working | Yes | Large, active feed; AI/data tags present | **✅ Implemented — Phase 1.** Public JSON API, no auth. ToS requires a backlink to RemoteOK if results are ever shown publicly (e.g. a future dashboard); not relevant for a private Telegram digest. |
| **WeWorkRemotely** | ✅ RSS by category, confirmed working (`/categories/remote-programming-jobs.rss`) | – | Yes | Mostly mid/senior — filtering matters | **✅ Implemented — Phase 2b.** RSS parsed with the standard-library XML parser (title is "Company: Position", plus region/category/pubDate/link) — no extra dependency needed. |
| **HelloWorld.rs** | Not found | Not found | Yes (no block on postings) | Original recon found a "Prakse" (internships) page. **What was actually found during implementation:** the site also has a dedicated **AI/ML tag view** at `/oglasi-za-posao/aiml` (a real filter — 19 postings vs. 30 on the generic list, verified by comparing results) — a much better-targeted source than the generic listing, and more important than the internships page alone. | **✅ Implemented — Phase 2b** (scraping both `/oglasi-za-posao/aiml` and `/prakse`, not the generic listing). Parsed via BeautifulSoup, anchored on stable GA4-tracking CSS classes (`__ga4_job_title`, etc.) rather than fragile Tailwind utility classes, since some fields (e.g. company link) inconsistently omit their class attribute — the parser falls back to DOM structure (`<h3>`→next `<h4>`) in that case. |
| **poslovi.infostud.com** | Blocked by robots.txt (`Disallow: /rss_feed/*`) | Not documented, but the page embeds a **Next.js `__NEXT_DATA__` JSON blob** with full structured job data — used instead of HTML scraping, much more robust | **Partial** — `/search/*` is blocked, but category pages like `/oglasi-za-posao-it/beograd` are **not** blocked | The generic IT/Belgrade category has 111 postings with low junior signal, as originally found. But Infostud shares its tag taxonomy with HelloWorld.rs (same company): filtering that same category page with `?tags=563` (AI/ML) and `?tags=340` (Prakse) narrows it to 10 + 6 targeted postings — same approach as HelloWorld.rs. | **✅ Implemented — Phase 2b**, using the two tag-filtered URLs, not the generic 111-posting category page. Parsed by extracting and JSON-decoding the `__NEXT_DATA__` script tag (`props.pageProps.initialSearchResults.jobs.primary`) rather than CSS selectors — gives clean structured fields (`onlineViewDate`, `itTags`, etc.) directly. |
| **Djinni.co** | Unclear | Unclear | **No** — robots.txt blocks exactly `/q` (search/query) and `/jobs2`, i.e. exactly what we'd need | Not measured (blocked by the decision rule before measuring) | **Skipped.** robots.txt explicitly forbids access to search. |
| **Wellfound** | None | Requires a partnership | **No** — blocks `/search`, `/jobs/applications`, `/jobs/signup` and filter parameters (`role`, `jobId`, `jobSlug`) | Not measured | **Skipped.** Same reason as Djinni — exactly what's needed is blocked. |
| **NoFluffJobs** | None | **No official public API** — only unofficial/paid scrapers (Apify etc.), outside our ToS tolerance | Site actively blocks automated access (fetch was refused) | Not measured | **Skipped.** |
| **ai-jobs.net (now "Foorilla")** | Unclear | A `/api/list/` link exists, but content/terms weren't reachable by automated check (looks JS-rendered) | Domain is a full 301 redirect to `foorilla.com` | Not measured | **Not pursued.** Left as a future option if it turns out to be worth checking manually — not blocking anything currently implemented. |
| **Startit.rs** | Unclear | None | Yes (no block) | **Inconsistent** — automated recon gave contradictory results (one page returned unrelated postings, another 404). The exact URL structure of the jobs section wasn't reliably established by tooling. | **Not pursued for now.** Low priority given 4 working sources already cover the target profile well; revisit if source diversity becomes a problem. |
| **LinkedIn / Indeed** | – | Closed to regular users | ToS forbids scraping | – | **Job alert emails = primary method (Phase 3)**, not scraping. Not yet implemented. |
| **SerpApi (Google Jobs)** | – | ✅ An official `engine=google_jobs` endpoint exists, confirmed by documentation | – (legitimate API, not scraping) | Free tier: **250 searches/month, 50/h throughput** — enough for a couple of queries once a day. **Coverage for Serbia untested** (needs a real API key) | **Secondary option — test with a real key in Phase 3.** Not yet implemented. |

**Phase 0.5 conclusion, updated:** implementation order was — **Phase 1:** RemoteOK. **Phase 2:** LLM ranking (moved ahead of additional sources, see section 3.1). **Phase 2b:** WeWorkRemotely, HelloWorld.rs, and Infostud — all three now live, each targeting the source's own best-signal view (AI/ML tag / internships) rather than a generic list wherever that option exists. Djinni, Wellfound, NoFluffJobs remain dropped (robots.txt/inaccessible). Startit.rs and Foorilla/ai-jobs.net remain unpursued, not currently a priority. **Phase 3** (LinkedIn/Indeed via job alert emails, SerpApi as a test) is the next real gap.

---

## 6. Running it — GitHub Actions

| Option | Pros | Cons |
|---|---|---|
| **GitHub Actions (chosen)** | Free at this scale (~60–90 min/month out of 2000 free for private repos), doesn't depend on your computer, Secrets built in, log history in the UI | Ephemeral runner → state has to be committed back; cron isn't precise |
| Local machine (Task Scheduler) | Easiest to try | The computer has to be on at the scheduled time — doesn't meet the requirement |
| VPS (Oracle Free Tier, Hetzner) | Most flexible | Maintenance, updates, security — unnecessary overhead |

### Concrete GitHub Actions gotchas to cover in the workflow

- **`workflow_dispatch` alongside `schedule` is mandatory.** Without it you'd wait for the cron to test during development. Saves hours.
- **Cron on an odd minute**, e.g. `17 5 * * *`, not `0 6 * * *`. Top-of-the-hour schedules are the most congested and tend to run late.
- **DST:** cron is in UTC, Serbia is UTC+1 in winter / UTC+2 in summer — delivery time shifts by an hour twice a year. Not a problem, just something to know.
- **`concurrency` group** + `git pull --rebase` before pushing, so runs don't collide over `seen.jsonl`.
- **60-day shutdown of scheduled workflows:** GitHub disables the `schedule` trigger after a period of repo inactivity. Whether bot commits (`github-actions[bot]`) count as activity wasn't confirmed — if they don't, the agent quietly dies after two months. Mitigation if needed: a monthly manual commit or a `workflow_dispatch` reminder. **Not yet verified in production** (the repo is under 2 months old as of this writing).
- **`--dry-run` flag** in the script: does everything except sending, logs the digest instead. Implemented from Phase 1.
- Failure notification: GitHub emails you when a workflow breaks — a free alerting layer.

**✅ Confirmed in production, beyond what was originally planned:** the `schedule` trigger is *much* less precise than expected — configured for 05:17 UTC, but observed runs consistently fire around 09:20–10:40 UTC instead (a 4–5 hour delay), every day for a week straight. This appears to be a free-tier/low-activity-repo scheduling reality, not an occasional fluke. Not fixed; documented as a known limitation (see README). A fix, if ever needed, would be an external pinger (e.g. cron-job.org) calling `workflow_dispatch` at the exact time — not implemented, since the daily digest doesn't need to be precisely timed.

Workflow flow (✅ implemented as described): checkout → setup Python → install deps → run the script → commit + push `data/seen.jsonl` as `github-actions[bot]`.

---

## 7. Phased implementation plan

### Phase 0 — Setup ✅ done
The user personally created the private GitHub repo and did the initial commit/push (see section 0 — the assistant doesn't run git commands). Telegram bot via BotFather + chat_id. GitHub Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). The assistant prepared the project structure + `config.yaml` skeleton locally, the user reviewed and committed them.

### Phase 0.5 — Source recon ✅ done
See section 5.

### Phase 1 — MVP: RemoteOK + Telegram ✅ done
RemoteOK API as the first source (no auth, legal, good signal). Fetch → normalize → two-key dedup in `seen.jsonl` → Layer 1 filter → Telegram digest with the defined message format. `--dry-run` from the start. GitHub Actions workflow with `schedule` + `workflow_dispatch` + state commit.

### Phase 2 — LLM ranking ✅ done
Layer 2 from section 3.1: target roles in `config.yaml`, one Gemini API call per posting, `score` + reason, a send threshold, sorting. Reason included in the message. **Switched from the originally planned Claude API to Google Gemini** (free tier) since the user doesn't have Anthropic API credits — functionally equivalent for this use case, and free at this call volume.

### Phase 2b — Additional sources ✅ done
WeWorkRemotely, HelloWorld.rs, and Infostud, all wired in via `fetch_all_jobs()` in `main.py` with per-source failure isolation (if one adapter breaks, the others still run). Adapter architecture as planned: each source is a function returning a standardized posting.

**Found only during implementation, not part of the original plan:** the Gemini free tier's 15 requests/minute limit gets hit in practice once three-plus sources are combined (confirmed live: 33 Layer-1-passed postings in one run triggered a 429). `agent/llm.py` now retries automatically using Google's suggested wait time from the error response, rather than failing the run.

### Phase 3 — LinkedIn/Indeed coverage + email (not started)
IMAP parsing of job alert emails (primary). SerpApi only if it proves useful. Email fallback for sending + error alerting. Per-source logging (fetched / filtered / sent).

### Phase 4 — Reliability (not started)
A "zero results" alert when a source that normally returns results returns 0 (a sign the scraper broke). Retry with backoff. Weekly summary on Fridays. Threshold/filter tuning based on real-world use.

### Phase 5 — Optional extensions (not started)
- **Application tracker** (`applied` / `rejected` / `interview` / `no response`, with dates and a follow-up reminder). Probably a **bigger win than any additional source** — the biggest loss in job searching is losing track of who responded and when a follow-up is due.
- Web dashboard.
- WhatsApp/Viber (only if a concrete reason comes up).

---

## 8. Risks and mitigation

| Risk | Mitigation |
|---|---|
| **Too few postings exist at all** for this profile | Measured in Phase 0.5 before building; if very low → widen the filter (Python/Data/general junior dev), not more sources |
| **Keyword filter misses relevant postings** | Two-layer strategy (broad filter + LLM judgment) instead of strict negative keywords |
| **Scraping gets blocked** (IP ban, CAPTCHA) | Once/day, transparent User-Agent, robots.txt respected, fallback to other sources, never bypassing protections |
| **HTML structure changes** → scraper returns 0 | Modular adapters + per-source failure isolation (✅ implemented in Phase 2b) + "zero results" alert (Phase 4, not yet built) |
| **API/service changes its format** (RemoteOK, etc.) | Source diversification + per-source logging |
| **LinkedIn/Indeed ToS** | Job alert emails instead of scraping; SerpApi only as a secondary option |
| **Merge conflict / state file corruption** | JSONL instead of binary SQLite; `concurrency` group; `pull --rebase` before push |
| **Duplicates between sources** | Two-key dedup (`source_key` + `logical_key`) — ✅ confirmed working, including within a single source that lists the same posting under two different tag filters |
| **Workflow silently dies after 60 days** | Not yet verified whether bot commits count as activity; monthly manual trigger as a fallback if it turns out to matter |
| **Cron runs late / DST shift** | ✅ Confirmed worse than expected in practice — see section 6. Accepted as-is; a daily digest doesn't need precise timing |
| **LLM cost gets out of control** | Layer 1 limits call volume; `max_calls_per_run` cap in `config.yaml`; free-tier model (Gemini) — cost risk replaced by a **rate-limit** risk instead, now handled with automatic retry |
| **You get used to ignoring the messages** | No empty digests are sent; a weekly summary instead of daily noise (Phase 4, not yet built) |
| **Legal/ethical risk** | Strictly personal use, 1 recipient, no redistribution, willing to disable a source on request |

---

## Next step

Phases 0 through 2b are done and live. The user is monitoring real-world output (starting the day after Phase 2b shipped) and will report back with feedback — likely candidates for the next round: tuning `llm.score_threshold` or the Layer 2 prompt criteria based on what turns out to be mis-scored, before moving on to Phase 3 (LinkedIn/Indeed via job alert emails) or Phase 4 (reliability / weekly summary).
