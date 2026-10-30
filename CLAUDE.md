# ns-trafic-data — drumski saobraćaj Novog Sada, na 5 minuta

Jezik projekta (kod, komentari, README, commit poruke): srpski, latinica.

- Izvor: `http://stari.ugzins.rs/SAUS/counters_georss_sr.xml` (rezerva `counters_georss_gps_sr.xml`, isti sadržaj).
  Stanje poslednjeg 5-minutnog intervala po traci; nema dnevnih zbirova. Detalji polja: README.
- `prikupljanje/citaj.py` čuva samo NOVE intervale (ključ id trake + kraj intervala, `podaci/poslednji.json`);
  `prikupljanje/sati.py` posle ponoći pravi satne zbirove za juče (sat = kraj sata, 1–24 lokalno, kao Excel „Interval data“).
- Samo standardna biblioteka Pythona u `prikupljanje/` — workflow ne instalira pakete (brzina, ~15 s po pokretanju).
- Okidač: cron-job.org → `workflow_dispatch` na `citaj.yml` u `1-59/5 * * * *`; GitHub `schedule` (:13, :43) je samo rezerva.
- Podaci se ne menjaju naknadno: fajlovi u `podaci/intervali/` se samo dodaju; ispravke idu u novi fajl ili satni obračun.
- Testovi: `python -m pytest -q tests` (uključuje strogu proveru workflow-a — GitHub odbacuje workflow sa duplim ključevima).
