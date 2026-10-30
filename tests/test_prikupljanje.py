"""Prikupljanje: parsiranje, provera fajla, čuvanje samo novih intervala, trake, satni zbirovi."""
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from prikupljanje import citaj, sati

TESTOVI = Path(__file__).parent
PRIMER = (TESTOVI / "primer.xml").read_bytes()
BICIKLI = (TESTOVI / "primer_bicikli.xml").read_bytes()


def _citaj_csv(put):
    with open(put, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_parsiranje():
    updated, unosi = citaj.parsiraj(PRIMER)
    assert updated == "2026-10-30T07:08:58Z" and len(unosi) == 2
    a, b = unosi
    assert a["id"] == "0014-21" and a["interval_utc"] == "2026-10-30T07:05:00Z" and a["traka"] == "v"
    assert (a["vozila_h"], a["brzina_kmh"], a["sledjenje_s"], a["zauzetost_promil"], a["stanje"]) == (516, 54, 6.1, 96, 2)
    assert (a["lat"], a["lon"], a["vmax"]) == (45.269733, 19.802174, 50)
    assert (b["lat"], b["lon"]) == (45.25, 19.8) and b["traka"] == "p" and b["roadDesc"] == "IIA 100"   # decimalni zarez


def test_odbija_bicikliste_i_html():
    citaj.proveri(PRIMER)
    with pytest.raises(citaj.Greska):
        citaj.proveri(BICIKLI)
    with pytest.raises(citaj.Greska):
        citaj.proveri(b"<html><body>Server Error</body></html>")


def test_samo_novi_intervali(tmp_path):
    t = datetime(2026, 10, 30, 7, 7, 30, tzinfo=timezone.utc)
    p, novih, _, n = citaj.sacuvaj(PRIMER, t, tmp_path)
    assert (novih, n) == (2, 2) and p.relative_to(tmp_path).as_posix() == "intervali/2026/10/30/0807.csv"
    assert [r["id"] for r in _citaj_csv(p)] == ["0040-12", "0014-21"]          # po kraju intervala
    assert list(_citaj_csv(p)[0]) == citaj.KOLONE_INTERVALA
    # isti fajl 5 min kasnije (brojači nisu poslali novo): ništa novo, bez novog fajla
    p2, novih2, _, _ = citaj.sacuvaj(PRIMER, t.replace(minute=12), tmp_path)
    assert p2 is None and novih2 == 0
    # jedna traka pošalje novi interval → samo ona
    novo = PRIMER.replace(b"<updated>2026-10-30T07:05:00Z</updated>", b"<updated>2026-10-30T07:10:00Z</updated>")
    p3, novih3, _, _ = citaj.sacuvaj(novo, t.replace(minute=13), tmp_path)
    assert novih3 == 1 and [r["interval_utc"] for r in _citaj_csv(p3)] == ["2026-10-30T07:10:00Z"]
    assert json.loads((tmp_path / "poslednji.json").read_text())["0014-21"] == "2026-10-30T07:10:00Z"


def test_trake_se_menjaju_samo_kad_treba(tmp_path):
    t = datetime(2026, 10, 30, 7, 7, tzinfo=timezone.utc)
    _, unosi = citaj.parsiraj(PRIMER)
    assert citaj.azuriraj_trake(unosi, "2026-10-30T07:07:00Z", tmp_path) == 2
    assert citaj.azuriraj_trake(unosi, "2026-10-30T07:12:00Z", tmp_path) == 0
    unosi[0]["vmax"] = 60
    assert citaj.azuriraj_trake(unosi, "2026-10-30T07:17:00Z", tmp_path) == 1
    r = {x["id"]: x for x in _citaj_csv(tmp_path / "trake.csv")}
    assert r["0014-21"]["vmax"] == "60" and r["0014-21"]["prvi_put_utc"] == "2026-10-30T07:07:00Z"
    assert t


def _interval(koren, folder, ime, redovi):
    put = koren / "intervali" / folder / f"{ime}.csv"
    put.parent.mkdir(parents=True, exist_ok=True)
    with open(put, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=citaj.KOLONE_INTERVALA)
        w.writeheader()
        w.writerows(redovi)


def test_satni_zbirovi(tmp_path):
    # 30. 10. (zimsko vreme, UTC+1): sat 09 lokalno = intervali sa krajem 08:05–09:00 UTC+1 = 07:05–08:00 UTC
    red = lambda t, v, b="0", s="1": {"interval_utc": t, "id": "0015-21", "vozila_h": v, "brzina_kmh": b,
                                       "sledjenje_s": "5", "zauzetost_promil": "100", "stanje": s}
    ceo = [red(f"2026-10-30T07:{m:02d}:00Z" if m < 60 else "2026-10-30T08:00:00Z", "120") for m in range(5, 61, 5)]
    _interval(tmp_path, "2026/10/30", "0900", ceo[:6])
    _interval(tmp_path, "2026/10/30", "0930", ceo[6:] + [red("2026-10-30T08:05:00Z", "600", "45", "3")])
    # sat 24 (23–24 h lokalno) stiže posle ponoći, u fajlu sledećeg dana
    _interval(tmp_path, "2026/10/31", "0002", [red("2026-10-30T23:00:00Z", "60")])
    r = {(x["sat"], x["id"]): x for x in sati.satni(date(2026, 10, 30), tmp_path)}
    s9 = r[(9, "0015-21")]
    assert s9["vozila"] == 120 and s9["intervala"] == 12 and s9["brzina_kmh"] == "" and s9["stanje_max"] == 1
    assert s9["ts_utc"] == "2026-10-30T08:00Z"
    s10 = r[(10, "0015-21")]
    assert s10["vozila"] == 50 and s10["intervala"] == 1 and s10["brzina_kmh"] == 45.0 and s10["stanje_max"] == 3
    assert r[(24, "0015-21")]["vozila"] == 5
    assert sati.sacuvaj_dan(date(2026, 10, 30), tmp_path).relative_to(tmp_path).as_posix() == "sati/2026/10/30.csv"


def test_kraj_sata():
    u = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    assert sati.kraj_sata(u("2026-10-30T08:00:00")) == u("2026-10-30T08:00:00")
    assert sati.kraj_sata(u("2026-10-30T08:05:00")) == u("2026-10-30T09:00:00")
