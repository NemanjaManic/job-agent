# Plan: AI agent za traženje poslova (Junior AI/ML Engineer + prakse)

Fokus: **Junior AI Engineer / Junior ML Engineer / prakse (internships)**, lokacija **Srbija + strani remote**, hosting preko **GitHub Actions**.

**Ključna pretpostavka koja oblikuje ceo dizajn:** za ovaj profil u Srbiji realno se očekuje **0–3 nova relevantna oglasa dnevno**, sa danima bez ijednog. To znači da problem nije *količina* nego *prepoznavanje relevantnog u šumu* — pa je strategija "širok filter + LLM presuda", a ne "uzak keyword filter". Ova pretpostavka se proverava u Fazi 0.5 pre nego što se napiše ozbiljniji kod.

---

## 0. Pravilo rada: ko commit-uje i push-uje na GitHub

**Sve `git commit` i `git push` operacije tokom razvoja izvršava isključivo korisnik. Claude Code (asistent) nikada sam ne pokreće te komande.**

Konkretno:
- **Kreiranje repoa (Faza 0):** korisnik sam kreira GitHub repo (preko github.com ili `gh repo create`) i radi initial commit/push. Asistent može da pripremi/napiše fajlove lokalno (kod, `config.yaml`, workflow YAML), ali ne izvršava `git init`, `git commit`, `git push` ni bilo koju drugu komandu koja menja git istoriju ili remote — čak ni uz prethodno odobrenje za sličnu radnju ranije u sesiji.
- **Tokom celog projekta:** svaka izmena koda koju asistent napravi ostaje kao lokalna, nekomit-ovana promena dok je korisnik lično ne pregleda i commit-uje/push-uje.
- **Izuzetak — automatski state commit u produkciji (Faza 1+):** kad agent bude deployovan, GitHub Actions workflow (`github-actions[bot]`) će svakodnevno sam commit-ovati i push-ovati ažurirani `data/seen.jsonl` (dedup state), preko ugrađenog, repo-ograničenog `GITHUB_TOKEN`-a — ovo je poseban, unapred dogovoren mehanizam (vidi sekciju 6), **ne** isto što i asistent koji push-uje umesto korisnika. Ti commit-i su potpuno vidljivi i jasno obeleženi:
  - autor je `github-actions[bot]` (poseban avatar, jasno odvojen od korisnikovog naloga u istoriji i "blame" pogledu),
  - normalna commit poruka i normalan diff — vidi se tačno šta je promenjeno,
  - token je ograničen samo na taj repo, nema pristup nalogu, drugim repoima, niti podešavanjima repoa osim onoga što je eksplicitno dozvoljeno u `permissions:` bloku workflow-a.

  **Potvrđeno sa korisnikom:** ovaj automatski bot-commit mehanizam je prihvaćen i ostaje deo dizajna.

### Kad nešto nije jasno — pitaj, ne pretpostavljaj
Ako u bilo kojoj fazi (izbor izvora, format filtera, ponašanje kod greške, sadržaj poruke, itd.) nešto nije eksplicitno pokriveno planom ili je dvosmisleno, asistent **pita korisnika** pre nego što donese odluku i implementira je — ne nagađa i ne bira "razumnu" opciju samoinicijativno kad postoji realna neizvesnost oko toga šta korisnik želi.

### Zaštita privatnih/osetljivih podataka
Asistent **ne objavljuje javno** (u public repou, public GitHub Actions logu, commit porukama, issue/PR opisima, ili bilo kom drugom javno vidljivom mestu) informacije koje bi mogle ugroziti korisnika — uključujući, ali ne ograničavajući se na:
- lične podatke (ime, email, telefon, adresu, CV/profil korisnika iz `config.yaml`),
- API ključeve, tokene, lozinke, app password-e — ovi idu isključivo u GitHub Secrets, nikad u kod, commit, log ili konfiguracioni fajl koji se commit-uje,
- sadržaj privatnog mejl inboxa (za IMAP parsiranje job alert mejlova iz sekcije 3),
- bilo šta iz internih razgovora/beleški koje korisnik ne bi želeo da bude javno vidljivo.

Repo je već planiran kao **privatni** (Faza 0), što je prva linija zaštite, ali ovo pravilo važi nezavisno od toga — npr. GitHub Actions logovi umeju da procure ili se slučajno učine javnim, pa se ni u njih ne ispisuju osetljivi podaci (koristiti GitHub Actions masking/secrets za sve što je tajno).

---

## 1. Tehnički stek i zašto

| Komponenta | Izbor | Zašto |
|---|---|---|
| Jezik | **Python 3.11+** | Najbolji ekosistem za parsing/scraping (`httpx`, `feedparser`, `BeautifulSoup`/`lxml`), radi glatko na `ubuntu-latest` runneru, bez kompajliranja |
| HTTP | `httpx` | Pozivi ka API-jima, preuzimanje HTML/RSS strana; ima ugrađen timeout/retry handling |
| Parsing | `feedparser` (RSS), `BeautifulSoup` (HTML fallback) | RSS je prioritet gde postoji — stabilniji od HTML scraping-a |
| Headless browser | **Ne koristiti** (ni Playwright) | JS-teški sajtovi se rešavaju preko posrednika ili se izostavljaju; browser na runneru je spor, krhak i signal da izvor ne treba scrape-ovati |
| Skladište za dedup | **`data/seen.jsonl`** (append-only JSON Lines), commit-ovan nazad u repo | Vidi sekciju 4 — namerno **ne** SQLite |
| Konfiguracija | `config.yaml` (pozicije, ključne reči, lokacije, izvori, pragovi) | Menjanje kriterijuma bez diranja koda |
| LLM rangiranje | Claude API (jeftiniji model), od Faze 2 | Vidi sekciju 3.1 |
| Slanje poruka | Telegram Bot API + `smtplib` email fallback | Vidi sekciju 2 |
| Orkestracija | GitHub Actions (`schedule` + `workflow_dispatch`) | Vidi sekciju 6 |
| Sekreti | GitHub Actions Secrets | Nikad u kodu/repo-u |

Nema Node.js, Docker-a, Postgres-a — overengineering za lični projekat ovog obima.

---

## 2. Slanje poruka

### Telegram (primarni kanal)
1. U Telegramu razgovor sa **@BotFather** → `/newbot` → ime i username → dobiješ **bot token**.
2. Pošalješ svom botu bilo koju poruku (npr. `/start`).
3. Otvoriš `https://api.telegram.org/bot<TOKEN>/getUpdates` → u JSON-u nađeš svoj **chat_id**.
4. Slanje = POST na `https://api.telegram.org/bot<TOKEN>/sendMessage` sa `chat_id` i `text` (podržava HTML/Markdown i linkove).
5. Token i chat_id → GitHub Secrets.

Besplatno, bez relevantnih limita za 1 digest dnevno.

### Format poruke (definisati u Fazi 1)
Po oglasu:
```
🔹 <b>Naziv pozicije</b> — Kompanija
📍 Lokacija / Remote  ·  🕒 objavljeno pre X dana  ·  izvor
💡 [1 rečenica: zašto je ovo relevantno za tebe]
🔗 link
```
**Starost oglasa je obavezno polje** — junior pozicije se popunjavaju brzo, oglas star tri nedelje ne vredi isto kao jučerašnji. Ako izvor ne daje datum, prikazati "datum nepoznat", ne izostaviti red.

### Ponašanje kad nema novih oglasa
**Ne šalji ništa.** Pri očekivanom obimu (često 0 novih dnevno), svakodnevna "0 novih" poruka te za nedelju dana nauči da ignorišeš bota — čime ceo projekat gubi smisao. Umesto toga: nedeljni sažetak petkom ("ove nedelje: 4 poslata, 31 filtriran, svi izvori zdravi") koji potvrđuje da agent radi.

### Email (fallback)
- Gmail SMTP + **App Password** (traži 2FA; obična lozinka ne radi), ~500 mejlova/dan limit — više nego dovoljno.
- Alternativa: SendGrid free tier (100/dan).
- Uloga: (a) fallback ako Telegram slanje padne, (b) error alerting kad run pukne.

### WhatsApp / Viber (samo napomena, ne implementirati)
WhatsApp Cloud API traži Meta Business nalog i verifikaciju, naplaćuje se preko besplatnog praga; Twilio naplaćuje po poruci; Viber zahteva da korisnik ručno subscribe-uje bota. Telegram pokriva potrebu — ovo ostaje u Fazi 5 samo ako se pojavi konkretan razlog.

---

## 3. Izvori oglasa i strategija filtriranja

Prioritet: **API > RSS > pažljiv scraping**.

> **Važno:** tabela ispod je *lista kandidata za proveru*, ne finalna lista izvora. Koji se izvori zaista implementiraju odlučuje se u **Fazi 0.5** na osnovu izmerenih podataka.

### Kandidati — Srbija/region
| Izvor | Očekivani metod | Napomena |
|---|---|---|
| poslovi.infostud.com | RSS po pretrazi (proveriti) ili scraping | Najveći job board u Srbiji, ima kategoriju "praksa" |
| HelloWorld.rs | Scraping | IT fokus, dosta entry pozicija |
| Startit.rs | RSS ili scraping | Startup/junior/praksa oglasi kojih nema drugde |
| Djinni.co | RSS po sačuvanoj pretrazi ili scraping | Popularan u regionu, dosta junior oglasa |
| NoFluffJobs | Javni JSON API | CEE fokus, pravno čisto |

### Kandidati — AI/ML i remote
| Izvor | Očekivani metod | Napomena |
|---|---|---|
| RemoteOK | **Javni JSON API**, bez auth-a | Najlakši start, koristi se kao MVP izvor |
| ai-jobs.net | RSS ako postoji, inače scraping | Dedikovan AI/ML board |
| WeWorkRemotely | RSS po kategoriji | Dosta mid/senior — filter bitan |
| Wellfound | Scraping (API traži partnerstvo) | Nizak prioritet |

### LinkedIn i Indeed
Oba **zabranjuju scraping u ToS-u** i imaju jaku anti-bot zaštitu; njihovi API-ji su zatvoreni za obične korisnike. Dve legitimne opcije, redosled po preporuci:

1. **Parsiranje job alert mejlova** (preporučeno) — ručno podesiš LinkedIn/Indeed job alerte na poseban mejl, agent čita taj inbox preko IMAP-a i parsira oglase. Besplatno, bez limita, pravno čisto jer ti sami sajtovi šalju te podatke. Ovo je *promovisano iz "nice to have" u primarno rešenje*.
2. **SerpApi / sličan Google Jobs agregator** — legalno, ali ima mesečni limit besplatnih upita i **neizvesnu pokrivenost za Srbiju**. Integrisati **samo ako Faza 0.5 potvrdi** da vraća smislene rezultate za tvoje upite.

Ne raditi: CAPTCHA solving, IP rotaciju, direktan scraping ova dva sajta.

### 3.1 Strategija filtriranja (dvoslojna)

Keyword filter sam po sebi ne radi za ovaj profil. Junior AI/ML pozicije se u Srbiji često oglašavaju kao "Python Developer", "Data Analyst", "Junior Software Engineer", "ML intern" — bez ijedne AI reči u naslovu. Agresivna lista negativnih reči (`senior`, `5+ years`, `lead`) poješće upravo one oglase koje želiš, jer oglasi često pominju "senior" u opisu tima.

- **Sloj 1 — širok, jeftin filter (kod):** propušta sve što je iole blizu (tech pozicije, junior/intern/entry signali, ili odsustvo jasnog senior signala). Cilj je *ne izgubiti ništa*, ne biti precizan. Očekivano: 20–50 oglasa dnevno prolazi.
- **Sloj 2 — LLM presuda (Claude API):** za svaki oglas iz Sloja 1, model dobija tvoj profil (CV/skill lista iz `config.yaml`) i tekst oglasa, i vraća `score` (0–10) + jednu rečenicu obrazloženja. Šalje se samo iznad praga (npr. 6+), sortirano po score-u; obrazloženje ide u Telegram poruku.

Trošak: 20–50 kratkih poziva dnevno jeftinom modelu je reda veličine centi mesečno. Zato je LLM rangiranje **pomereno iz Faze 5 u Fazu 2** — ono rešava centralni problem projekta, a ne kozmetiku.

### Pravna napomena (za sve scraping izvore)
- Pre implementacije proveriti `robots.txt` i ToS svakog sajta.
- Scraping: **1x dnevno**, realan User-Agent koji identifikuje bota i daje kontakt, bez paralelnih zahteva, bez redistribucije podataka (jedini primalac si ti).
- Ako sajt zabranjuje scraping ili počne da blokira — izvor se **isključuje ili zamenjuje**, zaštita se ne probija.

---

## 4. Skladište za dedup

**Format: `data/seen.jsonl`** — jedan JSON objekat po liniji, append-only.

Zašto ne SQLite (izmena u odnosu na raniju verziju plana): SQLite je binarni fajl. Commit-ovan u git pri svakom run-u znači punu novu kopiju u istoriji, nečitljiv diff i **nerešiv merge konflikt**. JSONL je tekstualan → diff pokazuje tačno šta je agent video kog dana, konflikt se rešava ručno, repo ne buja. Ako ikad zatrebaju upiti, SQLite se lokalno generiše iz JSONL-a.

Polja po zapisu:

| Polje | Opis |
|---|---|
| `source_key` | Hash od `source + normalized_url` — identitet oglasa na konkretnom izvoru |
| `logical_key` | Hash od normalizovanog `company + title + location` — vidi ispod |
| `source` | npr. `remoteok`, `infostud` |
| `title`, `company`, `location`, `url` | Osnovni podaci |
| `posted_date` | Datum objave ako izvor daje (nullable) |
| `first_seen_at` | Kad ga je agent prvi put video |
| `llm_score`, `llm_reason` | Rezultat Sloja 2 (nullable ako nije stigao do LLM-a) |
| `status` | `sent` / `filtered_keyword` / `filtered_llm` / `duplicate` |
| `sent_at` | Kad je poslat (nullable) |

**Dva ključa, ne jedan.** Hash samo od `source + url` propušta isti oglas koji se pojavi i na RemoteOK-u i na ai-jobs.net — dobio bi ga dvaput. Zato `logical_key`: lowercase, uklonjena interpunkcija, uklonjeni sufiksi tipa `(m/ž)`, `(remote)`, `- Belgrade`. Oglas je nov samo ako **oba** ključa nisu viđena.

Tok run-a: fetch → normalizuj → izračunaj oba ključa → odbaci viđene → Sloj 1 filter → Sloj 2 (LLM) → sortiraj po score-u → pošalji → **upiši sve nove zapise** (i poslate i odbačene, sa razlogom) → commit & push.

Odbačene čuvamo da se ne procesiraju ponovo sutra (štedi LLM pozive) i da možeš videti *zašto* nešto nije poslato.

---

## 5. Faza 0.5 — Izviđanje izvora (radi se pre koda)

Ovo je najvažniji dodatak planu. Bez ovoga se gradi 9 adaptera od kojih pola nema šta da vrati.

Ručno, u browseru, **bez pisanja koda** (~1–2h). Za svaki izvor iz sekcije 3 popuniti tabelu:

| Izvor | Ima RSS? | Ima API? | robots.txt dozvoljava? | Broj relevantnih oglasa u poslednjih 30 dana | Odluka |
|---|---|---|---|---|---|

"Relevantnih" = junior/intern AI, ML, data ili Python pozicija, Srbija ili remote otvoren za Srbiju.

Pravilo odluke:
- **0–2 oglasa za 30 dana** → izvor se preskače, bez obzira koliko je tehnički lak.
- **Ima API/RSS i ≥3 oglasa** → implementira se.
- **Samo scraping i ≥5 oglasa** → implementira se, ali kasnije (Faza 2b).

Takođe u ovoj fazi:
- Proveriti da li **Google Jobs / SerpApi** uopšte vraća smislene rezultate za "junior machine learning Serbia" i slične upite, i koliki je aktuelan besplatni limit. Ako je pokrivenost slaba → SerpApi ispada iz plana, ostaje samo parsiranje job alert mejlova.
- Podesiti LinkedIn i Indeed job alerte na poseban mejl (kreće da skuplja podatke odmah, dok se agent gradi).

Rezultat faze: konačna lista izvora sa redosledom implementacije, upisana u `config.yaml`.

---

## 6. Pokretanje — GitHub Actions

| Opcija | Prednosti | Mane |
|---|---|---|
| **GitHub Actions (izabrano)** | Besplatno za ovaj obim (~60–90 min/mesec od 2000 free za privatne repoe), ne zavisi od tvog računara, Secrets ugrađeni, log istorija u UI | Efemeran runner → state se mora commit-ovati nazad; cron nije precizan |
| Lokalni računar (Task Scheduler) | Najlakše za probu | Računar mora biti upaljen u zakazano vreme — ne zadovoljava zahtev |
| VPS (Oracle Free Tier, Hetzner) | Najfleksibilnije | Održavanje, update-i, bezbednost — nepotreban overhead |

### Konkretne GitHub Actions zamke koje treba pokriti u workflow-u

- **`workflow_dispatch` obavezno pored `schedule`.** Bez toga tokom razvoja čekaš cron da bi testirao. Ovo štedi sate.
- **Cron na neparan minut**, npr. `17 5 * * *`, ne `0 6 * * *`. Zakazivanja na pun sat su najopterećenija i znaju da kasne i po sat vremena.
- **DST:** cron je u UTC, Srbija je UTC+1 zimi / UTC+2 leti — vreme isporuke se pomera za sat dva puta godišnje. Nije problem, samo znaj.
- **`concurrency` grupa** + `git pull --rebase` pre push-a, da se run-ovi ne sudare oko `seen.jsonl`.
- **60-dnevno gašenje zakazanih workflow-ova:** GitHub gasi `schedule` trigger nakon perioda neaktivnosti repoa. Proveriti u Fazi 0.5 da li bot-commit-i (`github-actions[bot]`) računaju kao aktivnost — ako ne, agent tiho umire za dva meseca. Mitigacija ako treba: mesečni ručni commit ili `workflow_dispatch` podsetnik.
- **`--dry-run` flag** u skripti: radi sve osim slanja, ispisuje digest u log. Bez ovoga ćeš sebi poslati desetak test poruka dok podešavaš filtere.
- Failure notification: GitHub sam šalje mejl kad workflow pukne — besplatan sloj alertinga.

Tok workflow-a: checkout → setup Python → install deps → run skripte → commit + push `data/seen.jsonl` kao `github-actions[bot]`.

---

## 7. Fazni plan implementacije

### Faza 0 — Setup (~1h)
**Korisnik lično** kreira privatni GitHub repo i radi initial commit/push (vidi sekciju 0 — asistent ne izvršava git komande). Telegram bot preko BotFather-a + chat_id. GitHub Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Asistent priprema strukturu projekta + `config.yaml` skeleton lokalno, korisnik ih pregleda i commit-uje.

### Faza 0.5 — Izviđanje izvora (~1–2h, bez koda)
Vidi sekciju 5. **Ne preskakati.** Izlaz: finalna lista izvora + odluka o SerpApi + podešeni job alerti.

### Faza 1 — MVP: RemoteOK + Telegram (~3–5h)
RemoteOK API kao prvi izvor (bez auth-a, legalan, dobar signal). Fetch → normalizacija → dvoključni dedup u `seen.jsonl` → Sloj 1 filter → Telegram digest sa definisanim formatom poruke. `--dry-run` od početka. GitHub Actions workflow sa `schedule` + `workflow_dispatch` + commit state-a.
**Cilj:** end-to-end lanac radi sam, jednom dnevno.

### Faza 2 — LLM rangiranje (~3–4h)
Sloj 2 iz sekcije 3.1: profil u `config.yaml`, Claude API poziv po oglasu, `score` + obrazloženje, prag za slanje, sortiranje. Obrazloženje u poruci. Podešavanje praga na osnovu prvih nekoliko dana.
**Zašto pre dodatnih izvora:** kvalitet po oglasu vredi više od količine kad je količina ionako mala.

### Faza 2b — Dodatni izvori (~4–6h)
Samo izvori koje je Faza 0.5 odobrila. Adapter arhitektura: svaki izvor je funkcija koja vraća standardizovan oglas — lako dodavanje/uklanjanje i izolovan debug kad jedan pukne. Grupisanje poruke po score-u, ne po izvoru.

### Faza 3 — LinkedIn/Indeed pokrivenost + email (~4–5h)
IMAP parsiranje job alert mejlova (primarno). SerpApi samo ako je Faza 0.5 dala zeleno svetlo. Email fallback za slanje + error alerting. Logging po izvoru (fetched / filtered / sent).

### Faza 4 — Pouzdanost (~2–3h)
"Zero results" alert kad izvor koji obično vraća rezultate vrati 0 (znak da je scraper pukao). Retry sa backoff-om. Nedeljni sažetak petkom. Podešavanje filtera na osnovu par nedelja realne upotrebe.

### Faza 5 — Opciona proširenja
- **Tracker prijava** (`applied` / `rejected` / `interview` / `no response`, sa datumima i podsetnikom za follow-up). Ovo je verovatno **veći dobitak od bilo kog dodatnog izvora** — najveći gubitak u traženju posla je nepraćenje ko je odgovorio i kada treba poslati follow-up.
- Web dashboard.
- WhatsApp/Viber (samo ako se pojavi razlog).

---

## 8. Rizici i mitigacija

| Rizik | Mitigacija |
|---|---|
| **Premalo oglasa uopšte postoji** za ovaj profil | Faza 0.5 to meri pre nego što se gradi; ako je izmereno vrlo malo → širi filter (Python/Data/general junior dev), ne više izvora |
| **Keyword filter propušta relevantno** | Dvoslojna strategija (širok filter + LLM presuda) umesto strogih negativnih reči |
| **Scraping blokiran** (IP ban, CAPTCHA) | 1x/dnevno, transparentan User-Agent, robots.txt, fallback na druge izvore, bez probijanja zaštite |
| **HTML struktura se promeni** → scraper vraća 0 | Modularni adapteri + "zero results" alert (Faza 4) |
| **API/servis menja format** (RemoteOK, NoFluffJobs) | Diversifikacija izvora + logging po izvoru |
| **LinkedIn/Indeed ToS** | Job alert mejlovi umesto scraping-a; SerpApi samo kao sekundarna opcija |
| **Merge konflikt / korupcija state fajla** | JSONL umesto binarnog SQLite-a; `concurrency` grupa; `pull --rebase` pre push-a |
| **Duplikati između izvora** | Dvoključni dedup (`source_key` + `logical_key`) |
| **Workflow se tiho ugasi posle 60 dana** | Proveriti pravilo u Fazi 0.5; ako važi → podsetnik za mesečni ručni trigger |
| **Cron kasni / DST pomeranje** | Neparan minut u zakazivanju; prihvatiti ±sat, nebitno za dnevni digest |
| **LLM trošak izmakne kontroli** | Sloj 1 ograničava broj poziva; dnevni cap na broj LLM poziva u `config.yaml`; jeftiniji model |
| **Navikneš se da ignorišeš poruke** | Ne šalju se prazni digest-i; nedeljni sažetak umesto svakodnevnog šuma |
| **Pravni/etički rizik** | Strogo lična upotreba, 1 primalac, bez redistribucije, spremnost da se izvor isključi na zahtev |

---

## Sledeći korak

**Faza 0 + Faza 0.5.** Ti kreiraš i push-uješ GitHub repo (sekcija 0), podešavaš Telegram bota, zatim ručno izviđanje izvora — tek kad postoji izmerena tabela izvora kreće Faza 1 (RemoteOK + Telegram MVP).
