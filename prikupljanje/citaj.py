"""Jedno čitanje drumskog saobraćaja: preuzmi fajl, sačuvaj NOVE 5-minutne intervale.

    python -m prikupljanje.citaj                 # preuzimanje (GitHub Actions, na 5 min)
    python -m prikupljanje.citaj --iz-fajla x.xml

Izvor (Atom + GeoRSS, „Automatski brojači saobraćaja“, osvežava se na 5 min): po jedan unos za svaku TRAKU
sa stanjem poslednjeg 5-minutnog intervala — vozila/h, brzina, vreme sleđenja, zauzetost, stanje 1–6.
Isti interval se vidi u više uzastopnih čitanja (brojač koji kasni), pa se čuva samo prvi put
(ključ: id trake + kraj intervala; poslednji viđeni interval po traci je u podaci/poslednji.json).

Izlaz (podaci/):
  intervali/YYYY/MM/DD/HHMM.csv   novi intervali ovog čitanja (lokalni datum i vreme čitanja)
  trake.csv                       opis traka (naziv, smer, traka p/s/v, koordinate, vmax) — menja se samo kad se nešto promeni
  poslednji.json                  id trake → kraj poslednjeg sačuvanog intervala (UTC)
  citanja.csv                     dnevnik svakog pokretanja (i neuspelog)
  stanje.json                     kratak pregled za sajt (poslednje čitanje, čitanja po satu za 48 h) — mali, čita ga nasicu.rs
  greske.log                      opis greške

Samo standardna biblioteka Pythona (bez instaliranja paketa u workflow-u).
Izlazni kod: 0 = uspeh, 2 = preuzimanje ili parsiranje nije uspelo.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import konfig

log = logging.getLogger(__name__)

NS = {"atom": "http://www.w3.org/2005/Atom", "c": "http://www.mikrobit.si/schemas/counters/v1"}
# vrednosti po intervalu (čuvaju se uvek)
KOLONE_INTERVALA = ["interval_utc", "id", "vozila_h", "brzina_kmh", "sledjenje_s", "zauzetost_promil", "stanje"]
# opis trake (čuva se jednom, u trake.csv)
KOLONE_TRAKE = ["id", "location", "locationDesc", "locationID", "roadDesc", "direction", "directionDesc",
                "traka", "lat", "lon", "vmax", "prvi_put_utc"]
KOLONE_CITANJA = ["vreme_utc", "okidac", "izvor", "feed_updated_utc", "traka", "novih_intervala", "ishod"]


class Greska(Exception):
    pass


# ---------------------------------------------------------------- preuzimanje i provera

def proveri(data: bytes) -> None:
    """Atom fajl sa VOZILIMA (counters:occ), ne sa biciklistima (volume_today) i ne HTML stranica greške."""
    if b"<feed" not in data[:3000]:
        raise Greska(f"odgovor nije Atom feed (počinje sa {data[:60]!r})")
    if b"counters:volume_today" in data or b"<counters:occ>" not in data:
        raise Greska("fajl nije drumski saobraćaj (nema counters:occ ili ima volume_today)")


def preuzmi(pokusaji: int = konfig.POKUSAJI, pauza_s: float = konfig.PAUZA_S) -> tuple[bytes, str]:
    """(sadržaj, „glavni“ ili „rezerva“); krug glavni → rezervni fajl se ponavlja `pokusaji` puta."""
    greske = []
    for i in range(pokusaji):
        if i:
            time.sleep(pauza_s)
        for ime, url in (("glavni", konfig.URL), ("rezerva", konfig.URL_REZERVA)):
            try:
                zahtev = urllib.request.Request(url, headers={"User-Agent": konfig.USER_AGENT, "Cache-Control": "no-cache"})
                with urllib.request.urlopen(zahtev, timeout=konfig.TIMEOUT_S) as r:
                    data = r.read()
                proveri(data)
                return data, ime
            except Exception as e:  # noqa: BLE001
                greske.append(f"{ime}: {type(e).__name__}: {e}")
                log.warning(greske[-1])
    raise Greska(" | ".join(greske))


# ---------------------------------------------------------------- parsiranje

def _t(e: ET.Element, ime: str) -> str:
    x = e.find(f"c:{ime}", NS)
    return (x.text or "").strip() if x is not None and x.text else ""


def _broj(s: str) -> float | None:
    s = s.strip().replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _ceo(s: str) -> int | None:
    b = _broj(s)
    return int(b) if b is not None else None


def _traka(lane: str) -> str:
    """„(v)“ → „v“ (vozna), „(p)“/„(P)“ → „p“ (preticajna), „(s)“ → „s“ (srednja); prazno ako nije navedeno."""
    return lane.strip().strip("()").lower()


def parsiraj(data: bytes) -> tuple[str, list[dict]]:
    """(feed_updated_utc, unosi) — jedan unos po traci, sa vrednostima intervala i opisom trake."""
    koren = ET.fromstring(data)
    feed_updated = (koren.findtext("atom:updated", default="", namespaces=NS) or "").strip()
    unosi = []
    for e in koren.findall("atom:entry", NS):
        unosi.append({
            "id": (e.findtext("atom:id", default="", namespaces=NS) or "").strip(),
            "interval_utc": (e.findtext("atom:updated", default="", namespaces=NS) or "").strip(),
            "vozila_h": _ceo(_t(e, "volume")), "brzina_kmh": _ceo(_t(e, "speed")), "sledjenje_s": _broj(_t(e, "gap")),
            "zauzetost_promil": _ceo(_t(e, "occ")), "stanje": _ceo(_t(e, "state")),
            "location": _t(e, "location"), "locationDesc": _t(e, "locationDesc"), "locationID": _t(e, "locationID"),
            "roadDesc": _t(e, "roadDesc"), "direction": _t(e, "direction"), "directionDesc": _t(e, "directionDesc"),
            "traka": _traka(_t(e, "laneDesc")), "lat": _broj(_t(e, "geoX")), "lon": _broj(_t(e, "geoY")),
            "vmax": _ceo(_t(e, "vmax")),
        })
    return feed_updated, unosi


# ---------------------------------------------------------------- čuvanje

def _procitaj_json(put: Path) -> dict:
    try:
        return json.loads(put.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def azuriraj_trake(unosi: list[dict], sada: str, koren: Path) -> int:
    """Dopunjuje/menja trake.csv samo kad se pojavi nova traka ili se promeni opis; vraća broj promena."""
    put = koren / "trake.csv"
    postojece = {}
    if put.exists():
        with open(put, encoding="utf-8", newline="") as f:
            postojece = {r["id"]: r for r in csv.DictReader(f)}
    promena = 0
    for u in unosi:
        nov = {k: ("" if u.get(k) is None else str(u[k])) for k in KOLONE_TRAKE if k != "prvi_put_utc"}
        staro = postojece.get(u["id"])
        if staro is None:
            postojece[u["id"]] = {**nov, "prvi_put_utc": sada}
            promena += 1
        elif any(staro.get(k, "") != v for k, v in nov.items()):
            postojece[u["id"]] = {**nov, "prvi_put_utc": staro.get("prvi_put_utc", sada)}
            promena += 1
    if promena:
        with open(put, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=KOLONE_TRAKE)
            w.writeheader()
            w.writerows(sorted(postojece.values(), key=lambda r: r["id"]))
    return promena


def sacuvaj(data: bytes, sada_utc: datetime, koren: Path | None = None) -> tuple[Path | None, int, str, int]:
    """Čuva nove intervale ovog čitanja. Vraća (putanja CSV-a ili None, novih, feed_updated, ukupno traka)."""
    koren = koren or konfig.PODACI
    koren.mkdir(parents=True, exist_ok=True)
    feed_updated, unosi = parsiraj(data)
    poslednji_put = koren / "poslednji.json"
    poslednji = _procitaj_json(poslednji_put)
    novi = [u for u in unosi if u["id"] and u["interval_utc"] and u["interval_utc"] > poslednji.get(u["id"], "")]
    sada = f"{sada_utc:%Y-%m-%dT%H:%M:%SZ}"
    azuriraj_trake(unosi, sada, koren)
    put = None
    if novi:
        lok = sada_utc.astimezone(konfig.TZ)
        folder = koren / "intervali" / f"{lok:%Y}" / f"{lok:%m}" / f"{lok:%d}"
        folder.mkdir(parents=True, exist_ok=True)
        ime, i = f"{lok:%H%M}", 2
        while (folder / f"{ime}.csv").exists():
            ime, i = f"{lok:%H%M}_{i}", i + 1
        put = folder / f"{ime}.csv"
        with open(put, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=KOLONE_INTERVALA, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(novi, key=lambda u: (u["interval_utc"], u["id"])))
        for u in novi:
            poslednji[u["id"]] = u["interval_utc"]
        poslednji_put.write_text(json.dumps(dict(sorted(poslednji.items())), indent=0) + "\n", encoding="utf-8")
    return put, len(novi), feed_updated, len(unosi)


def upisi_citanje(koren: Path, red: dict) -> None:
    put = koren / "citanja.csv"
    nov = not put.exists()
    with open(put, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONE_CITANJA)
        if nov:
            w.writeheader()
        w.writerow(red)


def napravi_stanje(koren: Path, sada_utc: datetime, sati: int = 48) -> dict:
    """Pregled iz kraja citanja.csv: poslednje čitanje, poslednja greška i čitanja po lokalnom satu (najviše 12 na sat)."""
    put = koren / "citanja.csv"
    redovi = []
    if put.exists():
        with open(put, encoding="utf-8", newline="") as f:
            redovi = list(csv.DictReader(f))[-(sati * 15):]          # dovoljno za 48 h i uz dodatna pokretanja
    od = sada_utc.timestamp() - sati * 3600
    po_satu = {}
    for r in redovi:
        t = datetime.fromisoformat(r["vreme_utc"].replace("Z", "+00:00"))
        if t.timestamp() < od:
            continue
        k = t.astimezone(konfig.TZ).strftime("%Y-%m-%dT%H")
        s = po_satu.setdefault(k, {"sat": k, "citanja": 0, "greske": 0, "novih": 0})
        if r["ishod"] == "procitano":
            s["citanja"] += 1
            s["novih"] += int(r["novih_intervala"] or 0)
        else:
            s["greske"] += 1
    uspesna = [r for r in redovi if r["ishod"] == "procitano"]
    neuspesna = [r for r in redovi if r["ishod"] != "procitano"]
    return {
        "napravljeno_utc": f"{sada_utc:%Y-%m-%dT%H:%M:%SZ}",
        "poslednje": ({k: uspesna[-1][k] for k in ("vreme_utc", "okidac", "izvor", "feed_updated_utc", "traka", "novih_intervala")}
                      if uspesna else None),
        "poslednja_greska": neuspesna[-1]["vreme_utc"] if neuspesna else None,
        "sati": sorted(po_satu.values(), key=lambda x: x["sat"]),
    }


def upisi_stanje(koren: Path, sada_utc: datetime) -> None:
    (koren / "stanje.json").write_text(json.dumps(napravi_stanje(koren, sada_utc), ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")


def okidac() -> str:
    """cron-job.org (workflow_dispatch), rezerva (schedule) ili ručno/lokalno."""
    return {"workflow_dispatch": "cron-job.org", "schedule": "rezerva"}.get(os.environ.get("GITHUB_EVENT_NAME", ""), "rucno")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iz-fajla", type=Path, help="umesto preuzimanja koristi lokalni XML (za proveru)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    koren = konfig.PODACI
    koren.mkdir(parents=True, exist_ok=True)
    sada = datetime.now(timezone.utc).replace(microsecond=0)
    red = {"vreme_utc": f"{sada:%Y-%m-%dT%H:%M:%SZ}", "okidac": okidac(), "izvor": "", "feed_updated_utc": "",
           "traka": "", "novih_intervala": "", "ishod": ""}
    try:
        if a.iz_fajla:
            data, izvor = a.iz_fajla.read_bytes(), "fajl"
            proveri(data)
        else:
            data, izvor = preuzmi()
        put, novih, feed_updated, n = sacuvaj(data, datetime.now(timezone.utc).replace(microsecond=0), koren)
    except Exception as e:  # noqa: BLE001
        poruka = " ".join(f"{type(e).__name__}: {e}".split())[:600]
        with open(koren / "greske.log", "a", encoding="utf-8") as f:
            f.write(f"{red['vreme_utc']}\t{poruka}\n")
        upisi_citanje(koren, {**red, "ishod": "greska"})
        upisi_stanje(koren, sada)
        log.error("čitanje nije uspelo: %s", poruka)
        return 2
    upisi_citanje(koren, {**red, "izvor": izvor, "feed_updated_utc": feed_updated, "traka": n,
                          "novih_intervala": novih, "ishod": "procitano"})
    upisi_stanje(koren, sada)
    log.info("traka: %d, novih intervala: %d%s", n, novih, f" → {put.relative_to(koren).as_posix()}" if put else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
