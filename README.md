# ns-trafic-data — drumski saobraćaj Novog Sada, na 5 minuta

Automatsko prikupljanje javnih podataka sa **automatskih brojača saobraćaja** Novog Sada (UGZ / Mikrobit):
na svakih 5 minuta se preuzme stanje svih traka i trajno sačuva u ovom repozitorijumu.
Sestrinski projekat: [ns-bike-data](https://github.com/vijukM/ns-bike-data) (biciklisti, sajt nasicu.rs).

## Izvor

| | |
|---|---|
| Glavni fajl | `http://stari.ugzins.rs/SAUS/counters_georss_sr.xml` |
| Rezerva | `http://stari.ugzins.rs/SAUS/counters_georss_gps_sr.xml` — **isti sadržaj**, samo sa decimalnim zarezom u koordinatama |
| Oblik | Atom + GeoRSS, „Automatski brojači saobraćaja“, ~230 kB |
| Osvežavanje | na 5 minuta |

Jedan unos = jedna **traka** (oktobar 2026: 172 trake na 44 lokacije). Svaki unos je stanje **poslednjeg
5-minutnog intervala** — fajl nema dnevnih zbirova (za razliku od fajla sa biciklistima), pa se pun sat dobija
samo čitanjem na svakih 5 minuta.

| Polje u izvoru | Kolona | Značenje |
|---|---|---|
| `id` | `id` | traka: lokacija-smer, npr. `0015-21` (smer = strana × 10 + traka: 21 = strana b, traka 1) |
| `updated` | `interval_utc` | **kraj** 5-minutnog intervala (UTC) |
| `volume` | `vozila_h` | broj vozila preračunat na sat (vozila u intervalu = vozila_h / 12) |
| `speed` | `brzina_kmh` | prosečna brzina; **0 = brojač ne meri brzinu** (većina traka) |
| `gap` | `sledjenje_s` | prosečno vreme sleđenja vozila (s) |
| `occ` | `zauzetost_promil` | zauzetost trake u promilima (96 = 9,6 %) |
| `state` | `stanje` | 1 normalno · 2 povećan intenzitet · 3 gust · 4 otežano · 5 otežano sa zastojima · 6 nema saobraćaja |
| `laneDesc` | `traka` | `p` preticajna · `s` srednja · `v` vozna (prazno ako nije navedeno) |
| `vmax`, `geoX/geoY`, opisi | u `trake.csv` | ograničenje brzine, koordinate, naziv lokacije i smera, oznaka puta |

**Veza sa Excel izvozom „Interval data“** (istorija UGZ-a, sat po sat): trake 1/2/3 = p/s/v, traka 4 = biciklisti
(nije u ovom fajlu, nego u fajlu sa biciklistima). Satni `vozila` iz ovog projekta odgovara koloni **S1–S3**,
`zauzetost_promil` koloni **OCC**, `sledjenje_s` koloni **GAP**. Klase vozila (A1/A2/B1/B2/C1/XX) i temperatura
uređaja **ne postoje** u javnom fajlu; brzina postoji samo u javnom fajlu.

## Podaci

```
podaci/
  intervali/2026/10/30/0905.csv   NOVI intervali iz čitanja u 09:05 (lokalno vreme čitanja)
                                  interval_utc, id, vozila_h, brzina_kmh, sledjenje_s, zauzetost_promil, stanje
  sati/2026/10/30.csv             satni zbirovi po traci za ceo dan (pravi se posle ponoći)
                                  datum, sat (1–24, KRAJ sata, kao u Excel-u), ts_utc, id, vozila, intervala (od 12),
                                  zauzetost_promil, sledjenje_s, brzina_kmh, stanje_max
  trake.csv                       opis svake trake; menja se samo kad se pojavi nova traka ili promeni opis
  poslednji.json                  id trake → kraj poslednjeg sačuvanog intervala (da se isti interval ne čuva dvaput)
  citanja.csv                     dnevnik SVAKOG pokretanja: vreme, okidač, izvor, traka, novih intervala, ishod
  greske.log                      opis greške kad čitanje ne uspe
```

- **Bez duplikata:** brojač koji kasni pokazuje isti interval u više čitanja; čuva se samo prvi put.
- **Rupa** = interval koji nijedno čitanje nije videlo (npr. pao server, kasnio GitHub). U satnim zbirovima
  kolona `intervala` kaže koliko je od 12 intervala ušlo; `vozila` je tada nepotpun zbir.
- **Vreme:** `interval_utc` i `ts_utc` su UTC; folderi i satne oznake su lokalno vreme (Europe/Belgrade).
  Dan prelaska na zimsko vreme ima sat 03 dva puta (razlikuju se po `ts_utc`), na letnje 23 sata.
- **Veličina:** jedno čitanje ≈ 8 kB, ≈ 2,5 MB nekompresovanih podataka dnevno; git ih kompresuje (≈ 0,5 MB/dan).

Čitanje iz Pythona (pandas):

```python
import pandas as pd, glob
dan = pd.concat(pd.read_csv(f) for f in sorted(glob.glob("podaci/intervali/2026/10/30/*.csv")))
sati = pd.read_csv("podaci/sati/2026/10/30.csv")
trake = pd.read_csv("podaci/trake.csv", dtype={"location": str})
```

## Kako radi

```
cron-job.org (svakih 5 min) ──POST──▶ GitHub API: workflow_dispatch citaj.yml
                                         │
                       GitHub Actions:  python3 -m prikupljanje.citaj   (preuzme, sačuva nove intervale)
                                        python3 -m prikupljanje.sati    (posle ponoći: satni zbirovi za juče)
                                        git commit + push podaci/
```

- **cron-job.org je samo „budilnik“**: pošalje jedan HTTP zahtev GitHub-u. Preuzimanje, obrada i commit se
  izvršavaju u GitHub Actions — za **javne** repozitorijume besplatno i bez limita minuta. Pokretanje traje ≈ 15 s
  (samo standardna biblioteka Pythona, bez instaliranja paketa).
- **Rezerva:** GitHub `schedule` u :13 i :43. GitHub ga ume zakasniti ili preskočiti, zato je samo rezerva
  (ako cron-job.org stane, i dalje se čuva bar po jedan interval na pola sata). Duplikata nema.
- `concurrency` sprečava preklapanje dva pokretanja; push ima 4 pokušaja sa `git pull --rebase`.
- Ako čitanje ne uspe (obe adrese, dva kruga): red u `citanja.csv` sa `ishod=greska`, opis u `greske.log`,
  a pokretanje je **crveno** u Actions (GitHub može da pošalje mejl).

## Cron-job.org — podešavanje (jednom)

### 1. Token za GitHub

GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** →
**Generate new token**:

- Repository access: **Only select repositories** → `ns-trafic-data`;
- Permissions → Repository permissions → **Actions: Read and write** (ostalo ne treba);
- Expiration: po želji — **zapišite datum isteka**; kad token istekne, cron-job.org dobija 401 i čitanja staju
  (ostaje samo rezerva na pola sata).

Može se koristiti i postojeći token od `ns-bike-data` ako mu se doda ovaj repozitorijum (Edit → Repository access).

### 2. Novi posao na cron-job.org

<https://console.cron-job.org/jobs/create>:

| Polje | Vrednost |
|---|---|
| Common → Title | `ns-trafic-data citaj` |
| Common → URL | `https://api.github.com/repos/vijukM/ns-trafic-data/actions/workflows/citaj.yml/dispatches` |
| Common → Enable job | uključeno |
| Common → Execution schedule | **Custom** → `1-59/5 * * * *` (u :01, :06, :11 … — minut posle osvežavanja fajla) |
| Advanced → Time zone | `Europe/Belgrade` |
| Advanced → Request method | `POST` |
| Advanced → Headers (svaki posebno, *Add header*) | `Authorization` = `Bearer <token>`<br>`Accept` = `application/vnd.github+json`<br>`X-GitHub-Api-Version` = `2022-11-28` |
| Advanced → Request body | `{"ref":"main"}` |
| Notifications (opciono) | mejl kad poziv ne uspe |

Zatim **Test run** → očekivan odgovor **`204 No Content`** → **Create**.

Provera: GitHub → Actions → **citaj** — na 5 minuta novo pokretanje (zeleno), a u `podaci/citanja.csv` red
sa `okidac=cron-job.org`. Isto iz terminala:

```bash
curl -i -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/vijukM/ns-trafic-data/actions/workflows/citaj.yml/dispatches \
  -d '{"ref":"main"}'
```

| Odgovor | Značenje |
|---|---|
| `204` | u redu, pokretanje je zakazano |
| `401` | token je pogrešan ili je istekao |
| `403` | token nema dozvolu „Actions: Read and write“ za ovaj repozitorijum |
| `404` | pogrešan URL (ime repozitorijuma ili workflow-a) ili token ne vidi repozitorijum |
| `422` | `ref` nije postojeća grana (mora biti `main`) |

**Zašto `1-59/5`, a ne `*/5`:** izvor se osvežava oko :00, :05, :10…; minut kasnije je novi interval sigurno tu.
Ni kašnjenje GitHub-a od 1–2 min ne smeta — sledeće čitanje uhvati sve što je propušteno.

## Lokalno

```bash
python3 -m prikupljanje.citaj                    # jedno čitanje (piše u podaci/)
python3 -m prikupljanje.citaj --iz-fajla x.xml   # bez preuzimanja
python3 -m prikupljanje.sati --dan 2026-10-30    # satni zbirovi za zadati dan
pip install pytest pyyaml && python -m pytest -q tests
```
