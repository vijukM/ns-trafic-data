"""Zajednička podešavanja: izvori, putanje, vremenska zona."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Isti sadržaj na dve adrese; rezervna ima decimalni zarez u koordinatama.
URL = "http://stari.ugzins.rs/SAUS/counters_georss_sr.xml"
URL_REZERVA = "http://stari.ugzins.rs/SAUS/counters_georss_gps_sr.xml"
USER_AGENT = os.environ.get(
    "NS_TRAFIC_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
)
TIMEOUT_S = 30
POKUSAJI = 2           # krug (glavni, pa rezervni fajl) se ponavlja toliko puta
PAUZA_S = 20           # pauza između krugova

TZ = ZoneInfo("Europe/Belgrade")
KOREN = Path(__file__).resolve().parent.parent
PODACI = Path(os.environ.get("NS_TRAFIC_PODACI", KOREN / "podaci"))
