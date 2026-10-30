"""Satni zbirovi po traci iz 5-minutnih intervala → podaci/sati/YYYY/MM/DD.csv (lokalni dan).

    python -m prikupljanje.sati                  # juče i prethodnih 7 dana kojima fali satni fajl (posle ponoći)
    python -m prikupljanje.sati --dan 2026-10-30 # zadati dan (prepisuje)

Oznaka sata je KRAJ sata, 01–24 lokalno (kao u Excel izvozu „Interval data“): interval 07:55–08:00 pripada satu 08.
Dan prelaska na zimsko vreme ima sat 03 dva puta (razlikuju se po ts_utc), na letnje 23 sata.
Kolone:
  datum, sat, ts_utc   lokalni dan, sat 1–24 (kraj sata), kraj sata u UTC
  id                   traka (kao u trake.csv: lokacija-smer, npr. 0015-21)
  vozila               zbir vozila u satu = Σ vozila_h / 12 (uporedivo sa S1–S3 iz Excel-a); prazno ako nema intervala
  intervala            koliko 5-minutnih intervala je ušlo (12 = ceo sat; manje = rupa, vrednost je nepotpuna)
  zauzetost_promil     prosek zauzetosti (kao OCC), sledjenje_s prosek vremena sleđenja (kao GAP)
  brzina_kmh           prosek brzine intervala sa brzinom > 0 (prazno ako brojač ne meri brzinu)
  stanje_max           najlošije stanje u satu (1 normalno … 5 otežano sa zastojima, 6 nema saobraćaja)
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import konfig

log = logging.getLogger(__name__)

KOLONE = ["datum", "sat", "ts_utc", "id", "vozila", "intervala", "zauzetost_promil", "sledjenje_s", "brzina_kmh", "stanje_max"]


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def kraj_sata(interval_utc: datetime) -> datetime:
    """Kraj sata kome pripada 5-minutni interval koji se završava u `interval_utc` (08:00 → 08:00, 08:05 → 09:00)."""
    pocetak = interval_utc - timedelta(minutes=5)
    return pocetak.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def granice_dana(d: date) -> tuple[datetime, datetime]:
    od = datetime(d.year, d.month, d.day, tzinfo=konfig.TZ).astimezone(timezone.utc)
    sutra = d + timedelta(days=1)
    do = datetime(sutra.year, sutra.month, sutra.day, tzinfo=konfig.TZ).astimezone(timezone.utc)
    return od, do


def intervali_dana(d: date, koren: Path) -> list[dict]:
    """Svi sačuvani intervali čiji SAT pripada lokalnom danu d (čitaju se fajlovi dana d i d+1 — sat 24 stiže posle ponoći)."""
    od, do = granice_dana(d)
    redovi = []
    for dan in (d, d + timedelta(days=1)):
        folder = koren / "intervali" / f"{dan:%Y}" / f"{dan:%m}" / f"{dan:%d}"
        for f in sorted(folder.glob("*.csv")):
            with open(f, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    k = kraj_sata(_utc(r["interval_utc"]))
                    if od < k <= do:
                        redovi.append({**r, "_kraj": k})
    return redovi


def _f(s: str) -> float | None:
    try:
        return float(s) if s not in ("", None) else None
    except ValueError:
        return None


def satni(d: date, koren: Path) -> list[dict]:
    grupe = defaultdict(dict)                     # (kraj sata, id) → interval_utc → red (bez duplikata)
    for r in intervali_dana(d, koren):
        grupe[(r["_kraj"], r["id"])][r["interval_utc"]] = r
    izlaz = []
    for (kraj, id_), po_intervalu in sorted(grupe.items()):
        rr = list(po_intervalu.values())
        voz = [_f(r["vozila_h"]) for r in rr if _f(r["vozila_h"]) is not None]
        zau = [_f(r["zauzetost_promil"]) for r in rr if _f(r["zauzetost_promil"]) is not None]
        sle = [_f(r["sledjenje_s"]) for r in rr if _f(r["sledjenje_s"]) is not None]
        brz = [_f(r["brzina_kmh"]) for r in rr if (_f(r["brzina_kmh"]) or 0) > 0]
        sta = [int(_f(r["stanje"])) for r in rr if _f(r["stanje"]) is not None]
        lok = kraj.astimezone(konfig.TZ)
        sat = 24 if lok.hour == 0 else lok.hour
        izlaz.append({
            "datum": d.isoformat(), "sat": sat, "ts_utc": f"{kraj:%Y-%m-%dT%H:%MZ}", "id": id_,
            "vozila": round(sum(voz) / 12) if voz else "", "intervala": len(rr),
            "zauzetost_promil": round(sum(zau) / len(zau), 1) if zau else "",
            "sledjenje_s": round(sum(sle) / len(sle), 1) if sle else "",
            "brzina_kmh": round(sum(brz) / len(brz), 1) if brz else "",
            "stanje_max": max(sta) if sta else "",
        })
    return izlaz


def sacuvaj_dan(d: date, koren: Path) -> Path | None:
    redovi = satni(d, koren)
    if not redovi:
        return None
    put = koren / "sati" / f"{d:%Y}" / f"{d:%m}" / f"{d:%d}.csv"
    put.parent.mkdir(parents=True, exist_ok=True)
    with open(put, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONE)
        w.writeheader()
        w.writerows(redovi)
    return put


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dan", type=date.fromisoformat, help="zadati lokalni dan (prepisuje postojeći fajl)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    koren = konfig.PODACI
    if a.dan:
        dani = [a.dan]
    else:
        # posle ponoći: juče i stariji dani bez satnog fajla (ako je neki obračun propušten)
        danas = datetime.now(timezone.utc).astimezone(konfig.TZ).date()
        dani = [danas - timedelta(days=i) for i in range(1, 8)
                if not (koren / "sati" / f"{danas - timedelta(days=i):%Y/%m/%d}.csv").exists()]
    for d in dani:
        put = sacuvaj_dan(d, koren)
        if put:
            log.info("satni zbirovi %s → %s", d, put.relative_to(koren))
    return 0


if __name__ == "__main__":
    sys.exit(main())
