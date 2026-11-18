"""Zajednička podešavanja: izvori, putanje, vremenska zona."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Isti sadržaj na dve adrese; rezervna ima decimalni zarez u koordinatama.
URL = "http://stari.ugzins.rs/SAUS/counters_georss_sr.xml"
URL_REZERVA = "http://stari.ugzins.rs/SAUS/counters_georss_gps_sr.xml"
URL_REZERVA_EN = "http://stari.ugzins.rs/SAUS/counters_georss_en.xml"   # isti podaci, engleski opisi stanja
IZVORI = (("glavni", URL), ("rezerva", URL_REZERVA), ("rezerva_en", URL_REZERVA_EN))
# Kolektor se otvoreno predstavlja: ko čita, zašto i kako da nas kontaktiraju (server vidi ovo u svom logu).
# Promena bez izmene koda: promenljiva okruženja NS_TRAFIC_USER_AGENT (npr. u workflow-u).
USER_AGENT = os.environ.get(
    "NS_TRAFIC_USER_AGENT",
    "NaSicu/1.0 (+https://nasicu.rs; master rad, FTN Novi Sad; info@nasicu.rs)",
)
TIMEOUT_S = 20          # 2 kruga × 3 adrese × 20 s + pauza staju u timeout posla (4 min)
POKUSAJI = 2           # krug (glavni, pa rezervni fajl) se ponavlja toliko puta
PAUZA_S = 20           # pauza između krugova

TZ = ZoneInfo("Europe/Belgrade")
KOREN = Path(__file__).resolve().parent.parent
PODACI = Path(os.environ.get("NS_TRAFIC_PODACI", KOREN / "podaci"))
