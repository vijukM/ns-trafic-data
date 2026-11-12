"""Propušteni 5-minutni intervali (rupe u prikupljanju) → podaci/propusteno.csv i pregled u stanje.json.

    python -m prikupljanje.rupe          # ceo period → podaci/propusteno.csv (pokreće se posle ponoći)

Izvor daje samo POSLEDNJI interval po traci, pa se interval koji nijedno čitanje nije uhvatilo kasnije ne može
preuzeti — zato se rupe samo beleže (vrednosti ostaju prazne, satni zbir ima `intervala` < 12). Interval je propušten
kad ga nema ni za jednu traku (ceo grad); pojedinačne trake koje kasne ili ne javljaju ovde se ne broje.

Uzrok se procenjuje iz podaci/citanja.csv: čitanja posle kraja prvog propuštenog intervala, do 5 min posle poslednjeg:
  nije_pokrenuto  — nijedno pokretanje nije stiglo do čitanja (npr. GitHub „startup_failure“ ili kašnjenje Actions-a)
  izvor_greska    — čitanje je pokrenuto, ali izvor nije odgovorio ili je vratio pogrešan fajl (greske.log)
  izvor_nije_osvezio — čitanja su uspela, ali izvor nije objavio taj interval (vraćao je stariji fajl)
"""
from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import konfig

log = logging.getLogger(__name__)

KORAK = timedelta(minutes=5)
KOLONE = ["od_utc", "do_utc", "od_lokalno", "do_lokalno", "intervala", "uzrok"]


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _z(t: datetime) -> str:
    return f"{t:%Y-%m-%dT%H:%M:%SZ}"


def intervali(koren: Path, od: datetime | None = None) -> set[datetime]:
    """Krajevi svih sačuvanih intervala (bar jedna traka), od dana `od` (lokalni dan fajla) nadalje."""
    out: set[datetime] = set()
    granica = od.astimezone(konfig.TZ).strftime("%Y/%m/%d") if od else ""
    for f in sorted((koren / "intervali").glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/*.csv")):
        if f.parent.relative_to(koren / "intervali").as_posix() < granica:
            continue
        with open(f, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                out.add(_utc(r["interval_utc"]))
    return out


def citanja(koren: Path) -> list[tuple[datetime, str]]:
    put = koren / "citanja.csv"
    if not put.exists():
        return []
    with open(put, encoding="utf-8", newline="") as f:
        return [(_utc(r["vreme_utc"]), r["ishod"]) for r in csv.DictReader(f)]


def nadji(koren: Path, od: datetime | None = None, do: datetime | None = None) -> list[dict]:
    """Rupe (uzastopni propušteni intervali) između prvog i poslednjeg sačuvanog intervala (ili [od, do])."""
    ima = intervali(koren, od)
    if not ima:
        return []
    t, kraj = (od or min(ima)), (do or max(ima))
    t = max(t, min(ima))
    t = t.replace(second=0, microsecond=0) - timedelta(minutes=t.minute % 5)
    rupe: list[list[datetime]] = []
    while t <= kraj:
        if t not in ima:
            if rupe and t - rupe[-1][1] == KORAK:
                rupe[-1][1] = t
            else:
                rupe.append([t, t])
        t += KORAK
    cit = citanja(koren)
    out = []
    for a, b in rupe:
        u_prozoru = [i for v, i in cit if a < v <= b + KORAK]          # čitanja posle kraja intervala
        uzrok = ("nije_pokrenuto" if not u_prozoru else
                 "izvor_greska" if any(i != "procitano" for i in u_prozoru) else "izvor_nije_osvezio")
        out.append({"od_utc": _z(a), "do_utc": _z(b),
                    "od_lokalno": a.astimezone(konfig.TZ).strftime("%Y-%m-%d %H:%M"),
                    "do_lokalno": b.astimezone(konfig.TZ).strftime("%Y-%m-%d %H:%M"),
                    "intervala": int((b - a) / KORAK) + 1, "uzrok": uzrok})
    return out


def sacuvaj(koren: Path) -> Path:
    put = koren / "propusteno.csv"
    with open(put, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONE)
        w.writeheader()
        w.writerows(nadji(koren))
    return put


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    put = sacuvaj(konfig.PODACI)
    with open(put, encoding="utf-8") as f:
        n = sum(1 for _ in f) - 1
    log.info("rupa: %d → %s", n, put.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
