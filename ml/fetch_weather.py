import argparse
from pathlib import Path
import pandas as pd
import requests

REGIONS = {
    "Tunis": (36.80, 10.18), "Sfax": (34.74, 10.76), "Sousse": (35.83, 10.64),
    "Gabes": (33.88, 10.10), "Tozeur": (33.92, 8.13), "Bizerte": (37.27, 9.87),
}
URL = "https://archive-api.open-meteo.com/v1/archive"

def fetch(region, lat, lon, start, end):
    r = requests.get(URL, params={
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "daily": "temperature_2m_max,temperature_2m_mean",
        "timezone": "Africa/Tunis"}, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"Erreur Open-Meteo pour {region} (HTTP {r.status_code}) : {r.text[:300]}")
    d = r.json()["daily"]
    return pd.DataFrame({"date": pd.to_datetime(d["time"]), "region": region,
                         "tmax": d["temperature_2m_max"], "tmean": d["temperature_2m_mean"]})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    out = Path(a.out) if a.out else Path(__file__).resolve().parent.parent / "data" / "raw" / "weather.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    frames = []
    for name, (lat, lon) in REGIONS.items():
        print(f"Téléchargement {name}...")
        frames.append(fetch(name, lat, lon, a.start, a.end))
    w = pd.concat(frames, ignore_index=True)

    missing = w.tmax.isna().sum()
    w["tmax"] = w.groupby("region")["tmax"].transform(lambda s: s.interpolate(limit=3))
    w.to_csv(out, index=False)
    print(f"OK : {len(w)} lignes, {w.region.nunique()} régions, "
          f"{w.date.min().date()} -> {w.date.max().date()}, {missing} valeurs tmax manquantes -> {out}")
    print(w.assign(m=w.date.dt.month).query("m == 7").groupby("region").tmax.mean().round(1).to_string())

if __name__ == "__main__":
    main()