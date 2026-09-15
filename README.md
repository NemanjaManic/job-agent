# job-agent

Lični agent koji svakog dana pretražuje oglase za **Junior AI/ML Engineer** pozicije i prakse, ocenjuje relevantnost preko LLM-a i šalje dnevni digest na Telegram — bez ijednog ručnog pretraživanja job board-ova.

## Kako radi

```
RemoteOK + WeWorkRemotely + HelloWorld.rs + Infostud → dedup (data/seen.jsonl) → Sloj 1: keyword filter → Sloj 2: LLM ocena → Telegram digest
```

1. **Dohvat** — svaki izvor je nezavisan adapter u `agent/sources/` (RemoteOK API, WeWorkRemotely RSS, HelloWorld.rs i Infostud scraping — oba ciljaju sajtov AI/ML tag i Prakse sekciju umesto generičke liste). `main.py` ih sve zove i spaja rezultate; ako jedan izvor pukne (npr. sajt promeni HTML), ostali nastavljaju normalno (`fetch_all_jobs` u `main.py`).
2. **Dedup** — svaki oglas dobija dva ključa (izvor+URL i normalizovan naziv+kompanija+lokacija); već viđeni se preskaču (`agent/dedup.py`).
3. **Sloj 1 (keyword filter)** — širok, namerno plitak filter po naslovu/tagovima (`agent/filters.py`, ključne reči u `config.yaml`). Cilj je da ništa relevantno ne promakne, ne da bude precizan.
4. **Sloj 2 (LLM ocena)** — svaki oglas koji prođe Sloj 1 ide na Google Gemini (`agent/llm.py`), koji vraća ocenu 0–10 i jednu rečenicu obrazloženja u odnosu na ciljane pozicije iz `config.yaml`. Ispod praga (`llm.score_threshold`) se odbacuje — ovde se odseca šum tipa "Junior Payroll Assistant" ili "Data Entry Clerk" koji Sloj 1 pogrešno propusti.
5. **Slanje** — ono što prođe oba sloja šalje se kao Telegram digest, sortirano od najrelevantnijeg (`agent/telegram.py`, `agent/format.py`).

Pokreće se automatski svaki dan preko GitHub Actions (`.github/workflows/daily.yml`), koji na kraju i sam commit-uje ažurirani `data/seen.jsonl`.

## Status

- ✅ Faza 1 — RemoteOK + Telegram (live)
- ✅ Faza 2 — LLM rangiranje relevantnosti (Gemini, live)
- ✅ Faza 2b — dodatni izvori: WeWorkRemotely (RSS), HelloWorld.rs i Infostud (oba AI/ML tag + Prakse, scraping) — live
- ⬜ Faza 3 — LinkedIn/Indeed (job alert mejlovi), email fallback

Pun plan, arhitektonske odluke i rizici: [`PLAN.md`](./PLAN.md).

## Setup

Potrebne promenljive (lokalno u `.env`, u produkciji u GitHub repo → Settings → Secrets and variables → Actions):

| Promenljiva | Za šta | Gde se dobija |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Slanje digest poruka | [@BotFather](https://t.me/BotFather) na Telegramu |
| `TELEGRAM_CHAT_ID` | Kome se šalje | `https://api.telegram.org/bot<TOKEN>/getUpdates` posle prve poruke botu |
| `GEMINI_API_KEY` | Sloj 2 ocena relevantnosti | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — besplatan tier, bez kartice |

```bash
cp .env.example .env   # pa popuni vrednosti
pip install -r requirements.txt
```

## Pokretanje lokalno

```bash
python main.py --dry-run   # radi sve, samo ispisuje digest u log — ne šalje ništa
python main.py --send      # forsira pravo slanje na Telegram bez obzira na config.yaml
python main.py             # koristi run.dry_run iz config.yaml
```

## Podešavanje

Sve što se često menja (ciljane pozicije, ključne reči, prag za LLM ocenu, izvori) živi u [`config.yaml`](./config.yaml) — ne treba dirati kod da bi se promenilo ponašanje agenta.

## Struktura

```
main.py                        orkestracija: fetch → dedup → filter → LLM → slanje → state
config.yaml                    sva podešavanja (bez koda)
agent/
  config.py                    učitavanje config.yaml i env kredencijala
  dedup.py                     ključevi za dedup + čitanje/pisanje data/seen.jsonl
  filters.py                   Sloj 1 — keyword filter
  llm.py                       Sloj 2 — ocena relevantnosti preko Gemini API-ja (sa retry na rate limit)
  format.py                    format Telegram poruke
  telegram.py                  slanje na Telegram Bot API
  sources/
    remoteok.py                 RemoteOK API adapter
    weworkremotely.py           WeWorkRemotely RSS adapter
    helloworld.py                HelloWorld.rs adapter (AI/ML tag + Prakse, scraping)
    infostud.py                  Infostud adapter (AI/ML tag + Prakse, __NEXT_DATA__ JSON)
data/seen.jsonl                dedup state, append-only, auto-commit iz GitHub Actions
.github/workflows/daily.yml    dnevni cron + workflow_dispatch za ručno pokretanje
```

## Poznata ograničenja

- GitHub Actions `schedule` trigger nije garantovano tačan — cron je podešen na 05:17 UTC, ali u praksi zna da kasni i po nekoliko sati (free tier, uobičajeno za repoe sa malo aktivnosti). Nije bag u kodu; ako smeta, rešenje je eksterni pinger (npr. cron-job.org) koji okida `workflow_dispatch` u tačno vreme.
- Gemini besplatan tier ima limit od **15 zahteva/minut**. `agent/llm.py` automatski čeka i ponavlja poziv kad se limit dostigne (Google sam kaže koliko sekundi da se sačeka), pa run samo malo duže traje tog dana — ne puca.
