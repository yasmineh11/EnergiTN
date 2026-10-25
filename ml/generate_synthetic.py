"""
ÉnergiTN - Générateur de données synthétiques de consommation (horaire).

Usage :
    python generate_synthetic.py                      # météo synthétique (hors-ligne)
    python generate_synthetic.py --weather weather.csv  # météo réelle Open-Meteo

Sorties (dossier data/synthetic/) :
    households.csv  : household_id, persona, region, ac_coef, ...
    readings.csv    : household_id, timestamp, kwh, is_holiday, is_outage, is_anomaly, is_synthetic
    holidays_used.csv : jours fériés appliqués
    outages_used.csv  : coupures d'électricité régionales (région, début, durée en heures)
    (is_outage = 1 -> coupure : kwh vaut 0 ; ce n'est PAS une valeur manquante)
    (is_anomaly = vérité terrain, réservée à l'évaluation, jamais une feature)
"""
import argparse, json, os
import numpy as np
import pandas as pd

REGIONS = {  # région : (latitude, longitude, Tmax annuelle moyenne, amplitude saisonnière) en °C
    # Tmax journalière : ~14-17 °C en janvier, 34-43 °C en juillet-août (étés récents chauds),
    # + vagues de chaleur à 45-50 °C. Approximations : préférez la VRAIE météo Open-Meteo (--weather).
    "Tunis":   (36.80, 10.18, 25.0, 10.5),
    "Sfax":    (34.74, 10.76, 26.0, 10.0),
    "Sousse":  (35.83, 10.64, 25.5, 10.0),
    "Gabes":   (33.88, 10.10, 27.5, 10.5),
    "Tozeur":  (33.92,  8.13, 30.0, 13.0),   # sud saharien : étés très chauds
    "Bizerte": (37.27,  9.87, 24.5,  9.5),
}

# Personas : à enrichir avec l'aide d'un LLM (il propose, vous validez les paramètres)
PERSONAS = {
    "etudiant_appartement": dict(base=0.10, evening=0.35, morning=0.10, ac=0.12, night_ac=0.5, weekend=1.15),
    "famille_5_villa":      dict(base=0.30, evening=0.90, morning=0.35, ac=0.55, night_ac=0.8, weekend=1.10),
    "couple_actif":         dict(base=0.15, evening=0.55, morning=0.20, ac=0.25, night_ac=0.6, weekend=1.20),
    "retraite_a_la_maison": dict(base=0.18, evening=0.45, morning=0.30, ac=0.30, night_ac=0.4, weekend=1.00),
}


# ---------------------------------------------------------------------------
# Jours fériés tunisiens
# Fixes : mêmes dates chaque année. Religieux : dates lunaires, à saisir par année.
# 2026 : vérifié sur le calendrier officiel publié ; 2024-2025 : à VÉRIFIER avant le rapport.
# Pour une autre année, ajoutez ses dates dans RELIGIOUS_HOLIDAYS.
# ---------------------------------------------------------------------------
FIXED_HOLIDAYS = [(1, 1), (3, 20), (4, 9), (5, 1), (7, 25), (8, 13), (10, 15), (12, 17)]
# (1er janv., Indépendance, Martyrs, Travail, République, Femme, Évacuation, Révolution)

RELIGIOUS_HOLIDAYS = {
    2024: ["2024-04-10", "2024-04-11", "2024-04-12",   # Aïd el-Fitr (3 jours)
           "2024-06-16", "2024-06-17",                 # Aïd el-Adha (2 jours)
           "2024-07-07",                               # Ras el Am el Hijri
           "2024-09-15"],                              # Mouled
    2025: ["2025-03-31", "2025-04-01", "2025-04-02",
           "2025-06-06", "2025-06-07",
           "2025-06-26",
           "2025-09-04"],
    2026: ["2026-03-20", "2026-03-21", "2026-03-22",
           "2026-05-27", "2026-05-28",
           "2026-06-16",
           "2026-08-25"],
}

def build_holidays(years):
    """Retourne un set de dates (Timestamp) fériées pour les années demandées."""
    days = set()
    for y in years:
        for m, d in FIXED_HOLIDAYS:
            days.add(pd.Timestamp(y, m, d))
        for iso in RELIGIOUS_HOLIDAYS.get(y, []):
            days.add(pd.Timestamp(iso))
        if y not in RELIGIOUS_HOLIDAYS:
            print(f"ATTENTION : fêtes religieuses {y} non renseignées (seuls les jours fixes sont utilisés).")
    return days

def synth_weather(dates, region, rng):
    """Température max journalière simulée (hors-ligne). Préférez la vraie météo (--weather)."""
    lat, lon, tmax_mean, amp = REGIONS[region]
    doy = dates.dayofyear.values
    tmax = tmax_mean + amp * np.sin(2 * np.pi * (doy - 115) / 365)   # pic vers le 25 juillet-début août
    tmax = tmax + rng.normal(0, 2.5, len(dates))
    boost = np.zeros(len(dates))
    for yr in sorted(set(dates.year)):                                # 2 à 3 vagues de chaleur par été
        for _ in range(int(rng.integers(2, 4))):
            start = pd.Timestamp(yr, 6, 20) + pd.Timedelta(days=int(rng.integers(0, 60)))
            mask = (dates >= start) & (dates < start + pd.Timedelta(days=int(rng.integers(3, 8))))
            boost[mask] = np.maximum(boost[mask], rng.uniform(5, 10))  # pas d'addition : évite les valeurs absurdes
    tmax = np.minimum(tmax + boost, 50.0)                             # plafond réaliste
    return pd.DataFrame({"date": dates, "region": region, "tmax": tmax.round(1)})


# ---------------------------------------------------------------------------
# Coupures d'électricité (délestages, surcharge du réseau en période de canicule)
# Une coupure est un événement RÉGIONAL : elle touche la plupart des foyers de la région en même temps.
# Plus il fait chaud, plus la probabilité augmente ; durée de plusieurs heures ; début surtout l'après-midi/soir.
# Paramètres estimés (non calibrés sur des données officielles) : à ajuster et à documenter.
# ---------------------------------------------------------------------------
OUTAGE = dict(
    base_daily=0.04,     # probabilité de base par jour et par région (≈ 1 coupure toutes les 3-4 semaines)
    heat_daily=0.30,     # probabilité supplémentaire à pleine chaleur
    heat_from=33.0,      # °C : à partir de là, le risque monte
    heat_full=44.0,      # °C : risque maximal
    median_hours=2.5,    # durée médiane
    sigma=0.55,          # dispersion (quelques coupures longues)
    max_hours=10,
    hh_hit=0.85,         # part des foyers de la région touchés par une coupure
    rebound=1.25,        # pic de reprise : x1,25 pendant l'heure qui suit le retour du courant
)
START_HOUR_WEIGHTS = np.array([1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 4, 6, 7, 8, 8, 8, 8, 9, 10, 10, 9, 6, 3], dtype=float)
START_HOUR_WEIGHTS /= START_HOUR_WEIGHTS.sum()     # plus fréquentes entre 12h et 22h (pointe de demande)

def make_outage_events(wr, region, rng, rate):
    """Événements de coupure d'une région : liste de (région, début, durée en heures)."""
    events = []
    if rate <= 0:
        return events
    for date, tmax in zip(wr["date"], wr["tmax"]):
        t = 25.0 if pd.isna(tmax) else float(tmax)
        heat = min(1.0, max(0.0, (t - OUTAGE["heat_from"]) / (OUTAGE["heat_full"] - OUTAGE["heat_from"])))
        lam = (OUTAGE["base_daily"] + OUTAGE["heat_daily"] * heat) * rate
        for _ in range(int(rng.poisson(lam))):
            hour = int(rng.choice(24, p=START_HOUR_WEIGHTS))
            hours = int(np.clip(round(rng.lognormal(np.log(OUTAGE["median_hours"]), OUTAGE["sigma"])), 1, OUTAGE["max_hours"]))
            events.append((region, pd.Timestamp(date) + pd.Timedelta(hours=hour), hours))
    return events

def hourly_shape(h, p):
    morning = p["morning"] * np.exp(-((h - 7.5) ** 2) / 2.0)
    evening = p["evening"] * np.exp(-((h - 20.5) ** 2) / 4.0)
    return morning + evening

def simulate_household(hid, persona, region, ac_coef, wx, rng, start, end, anomaly_rate, holidays, events):
    p = PERSONAS[persona]
    ts = pd.date_range(start, end, freq="h")
    df = pd.DataFrame({"timestamp": ts})
    df["date"] = df.timestamp.dt.normalize()
    df = df.merge(wx[["date", "tmax"]], on="date", how="left")
    h = df.timestamp.dt.hour.values
    is_we = (df.timestamp.dt.dayofweek >= 5).values
    df["is_holiday"] = df.date.isin(holidays).astype(int)
    is_off = is_we | (df["is_holiday"].values == 1)      # week-end OU jour férié : on est à la maison
    # charge de base (frigo, veille) + habitudes
    kwh = p["base"] + hourly_shape(h, p) * np.where(is_off, p["weekend"], 1.0)
    # jour de repos : présence en journée (cuisine, télé, appareils) -> bosse vers 13h
    kwh = kwh + np.where(is_off, 0.5 * p["morning"] * np.exp(-((h - 13) ** 2) / 4.0), 0.0)
    # climatisation : proportionnelle au dépassement de 24 °C, surtout l'après-midi et le soir
    ac_hours = np.where((h >= 12) & (h <= 23), 1.0, np.where((h <= 2), p["night_ac"], 0.15))
    kwh = kwh + ac_coef * p["ac"] * np.clip(df.tmax.values - 24, 0, None) * ac_hours / 4
    # chauffage léger en hiver
    kwh = kwh + 0.03 * np.clip(14 - df.tmax.values, 0, None) * ((h >= 18) | (h <= 7))
    kwh = kwh * rng.lognormal(0, 0.12, len(df))                         # bruit multiplicatif
    df["kwh"] = kwh
    # anomalies injectées (vérité terrain)
    df["is_anomaly"] = 0
    n_days = (df.date.max() - df.date.min()).days
    for _ in range(int(n_days * anomaly_rate)):
        d0 = df.date.min() + pd.Timedelta(days=int(rng.integers(0, n_days - 5)))
        length = int(rng.integers(1, 5))
        kind = rng.choice(["night_load", "spike", "flat_high"])
        m = (df.date >= d0) & (df.date < d0 + pd.Timedelta(days=length))
        if kind == "night_load":   m &= (df.timestamp.dt.hour <= 5); df.loc[m, "kwh"] += rng.uniform(0.6, 1.2)
        elif kind == "spike":      df.loc[m, "kwh"] *= rng.uniform(2.2, 3.5)
        else:                      df.loc[m, "kwh"] = np.maximum(df.loc[m, "kwh"], rng.uniform(1.2, 2.0))
        df.loc[m, "is_anomaly"] = 1
    # trous de relevé réalistes (à nettoyer ensuite)
    miss = rng.random(len(df)) < 0.004
    df.loc[miss, "kwh"] = np.nan
    # coupures d'électricité : kWh = 0 (le compteur est vivant mais il n'y a pas de courant)
    outage = np.zeros(len(df), dtype=bool)
    t0 = df.timestamp.iloc[0]
    for _, st, hrs in events:
        if rng.random() < OUTAGE["hh_hit"]:
            i0 = int((st - t0).total_seconds() // 3600)
            if i0 + hrs > 0 and i0 < len(df):
                outage[max(i0, 0):max(i0 + hrs, 0)] = True
    rebound = np.roll(outage, 1) & ~outage
    rebound[0] = False
    df.loc[rebound, "kwh"] = df.loc[rebound, "kwh"] * OUTAGE["rebound"]   # pic de reprise
    df.loc[outage, "kwh"] = 0.0
    df.loc[outage, "is_anomaly"] = 0                                       # une coupure n'est pas une anomalie de conso
    df["is_outage"] = outage.astype(int)
    df["household_id"] = hid
    return df[["household_id", "timestamp", "kwh", "is_holiday", "is_outage", "is_anomaly"]]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--households", type=int, default=30)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-09-30 23:00")
    ap.add_argument("--weather", default=None, help="CSV Open-Meteo (date, region, tmax)")
    ap.add_argument("--anomaly-rate", type=float, default=0.02)
    ap.add_argument("--outage-rate", type=float, default=1.0, help="multiplicateur de fréquence des coupures (0 = aucune)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/synthetic")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.out, exist_ok=True)

    dates = pd.date_range(a.start, a.end, freq="D").normalize().unique()
    if a.weather:
        w = pd.read_csv(a.weather, parse_dates=["date"])
    else:
        w = pd.concat([synth_weather(dates, r, rng) for r in REGIONS])
    w.to_csv(os.path.join(a.out, "weather_used.csv"), index=False)

    years = sorted(set(dates.year))
    holidays = build_holidays(years)
    pd.DataFrame({"date": sorted(holidays)}).query("date >= @dates.min() and date <= @dates.max()") \
        .to_csv(os.path.join(a.out, "holidays_used.csv"), index=False)

    events = {rg: make_outage_events(w[w.region == rg], rg, rng, a.outage_rate) for rg in REGIONS}
    ev = pd.DataFrame([e for lst in events.values() for e in lst], columns=["region", "start", "hours"])
    ev.sort_values(["region", "start"]).to_csv(os.path.join(a.out, "outages_used.csv"), index=False)

    hh, parts = [], []
    for i in range(a.households):
        persona = rng.choice(list(PERSONAS)); region = rng.choice(list(REGIONS))
        ac_coef = float(rng.uniform(0.6, 1.4)); hid = f"H{i+1:03d}"
        hh.append(dict(household_id=hid, persona=persona, region=region, ac_coef=round(ac_coef, 2), is_synthetic=True))
        parts.append(simulate_household(hid, persona, region, ac_coef, w[w.region == region], rng, a.start, a.end, a.anomaly_rate, holidays, events[region]))
    pd.DataFrame(hh).to_csv(os.path.join(a.out, "households.csv"), index=False)
    r = pd.concat(parts); r["is_synthetic"] = True
    r.to_csv(os.path.join(a.out, "readings.csv"), index=False)
    print(f"{len(hh)} foyers, {len(r):,} relevés, {r.is_anomaly.mean():.1%} d'anomalies, "
          f"{r.kwh.isna().mean():.2%} de valeurs manquantes, {len(ev)} coupures régionales "
          f"({r.is_outage.mean():.2%} des heures, durée moyenne {ev.hours.mean() if len(ev) else 0:.1f} h) -> {a.out}")

if __name__ == "__main__":
    main()