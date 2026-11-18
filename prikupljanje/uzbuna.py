"""Da li neuspelo čitanje treba da bude crveno (i pošalje mejl), ili samo da se zabeleži.

    python3 -m prikupljanje.uzbuna      # izlaz 1 = uzbuna, 0 = samo zabeleženo

Kad izvor ne odgovara duže vreme, svako pokretanje na 5 min bi bilo crveno i slalo mejl. Uzbuna je zato samo za
PRVU grešku u nizu i zatim na svakih UZBUNA_NA uzastopnih grešaka (12 = jednom na sat). Niz se računa sa kraja
podaci/citanja.csv (poslednji redovi sa ishodom različitim od „procitano“).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import konfig

UZBUNA_NA = 12


def niz_gresaka(koren: Path) -> int:
    put = koren / "citanja.csv"
    if not put.exists():
        return 0
    with open(put, encoding="utf-8", newline="") as f:
        ishodi = [r["ishod"] for r in csv.DictReader(f)]
    n = 0
    for i in reversed(ishodi):
        if i == "procitano":
            break
        n += 1
    return n


def uzbuna(n: int) -> bool:
    return n == 1 or (n > 0 and n % UZBUNA_NA == 0)


def main() -> int:
    n = niz_gresaka(konfig.PODACI)
    if uzbuna(n):
        print(f"čitanje nije uspelo ({n}. zaredom) — vidi podaci/greske.log")
        return 1
    print(f"čitanje nije uspelo ({n}. zaredom) — zabeleženo, bez uzbune (sledeća na {((n // UZBUNA_NA) + 1) * UZBUNA_NA}.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
