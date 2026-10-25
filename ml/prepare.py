"""
ÉnergiTN - Étape 1 ML : préparation des données (CRISP-DM, phase 3).
Lit  : data/synthetic/{readings,households,weather_used}.csv
Écrit: data/processed/daily.csv   (une ligne par foyer et par jour, avec features de base)

Choix de nettoyage (à citer dans le rapport) :
 - doublons supprimés, valeurs négatives ou > 15 kWh/h (capteur) mises à NaN ;
 - heures de COUPURE (is_outage=1) et heure de REPRISE du courant (pic x1,25) : ce n'est pas la demande normale -> exclues ;
 - trous de compteur courts (<= 3 h) interpolés ; trous plus longs laissés vides ;
 - consommation du jour : somme des heures valides divisée par la part de la journée qu'elles représentent
   habituellement pour ce foyer (profil horaire par mois). Une coupure à la pointe du soir ne fausse donc plus
   le total ; on garde la journée si les heures valides couvrent au moins 60 % de la consommation habituelle.
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SYN, OUT = ROOT / "data" / "synthetic", ROOT / "data" / "processed"

def fill_short_gaps(s, maxgap=3):
    isna = s.isna()
    gap = isna.groupby((isna != isna.shift()).cumsum()).transform("sum")
    return s.where(~(isna & (gap <= maxgap)), s.interpolate(limit_area="inside"))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r = pd.read_csv(SYN / "readings.csv", parse_dates=["timestamp"])
    hh = pd.read_csv(SYN / "households.csv")
    w = pd.read_csv(SYN / "weather_used.csv", parse_dates=["date"])

    manquantes = [c for c in ("is_outage", "is_holiday", "is_anomaly") if c not in r.columns]
    if manquantes:
        raise SystemExit(f"readings.csv ne contient pas les colonnes {manquantes} : il vient d'une ancienne version du simulateur.\n"
                         "Remplacez generate_synthetic.py par la derniere version, puis relancez-le (voir le guide), avant prepare.py.")

    n0 = len(r)
    r = r.drop_duplicates(["household_id", "timestamp"]).sort_values(["household_id", "timestamp"])
    r.loc[(r.kwh < 0) | (r.kwh > 15), "kwh"] = np.nan
    # heures de coupure + heure de reprise (pic x1,25) : ce n'est pas la demande normale -> exclues
    g = r.groupby("household_id")
    rebound = (g.is_outage.shift(1).fillna(0) == 1) & (r.is_outage == 0)
    mask = (r.is_outage == 1) | rebound
    r["kwh_clean"] = r.kwh.where(~mask)
    filled = r.groupby("household_id")["kwh_clean"].transform(fill_short_gaps)   # trous de compteur <= 3 h
    r["kwh_clean"] = filled.where(~mask)
    r["date"] = r.timestamp.dt.normalize()
    r["hour"] = r.timestamp.dt.hour
    r["month"] = r.timestamp.dt.month

    # profil horaire habituel de chaque foyer (par mois) : part de la consommation du jour a chaque heure.
    # Sert a estimer la consommation d'une journee de coupure sans biais (la coupure tombe souvent a la pointe du soir).
    ok = (~mask) & (r.is_anomaly == 0) & r.kwh_clean.notna()
    prof = r[ok].groupby(["household_id", "month", "hour"]).kwh_clean.mean().rename("prof")
    prof = prof / prof.groupby(level=[0, 1]).transform("sum")
    r = r.merge(prof.rename("share").reset_index(), on=["household_id", "month", "hour"], how="left")
    r["share_valid"] = r.share.where(r.kwh_clean.notna())

    daily = (r.groupby(["household_id", "date"])
               .agg(valid_h=("kwh_clean", "count"), sum_k=("kwh_clean", "sum"), cover=("share_valid", "sum"),
                    outage_h=("is_outage", "sum"), is_holiday=("is_holiday", "max"),
                    anomaly_day=("is_anomaly", "max")).reset_index())
    night = (r[r.hour <= 5].groupby(["household_id", "date"]).kwh_clean.mean().rename("night_mean").reset_index())
    daily = daily.merge(night, on=["household_id", "date"], how="left")
    daily["kwh_day"] = np.where(daily.cover >= 0.6, daily.sum_k / daily.cover.replace(0, np.nan), np.nan)   # estimation par profil horaire

    w = w.sort_values(["region", "date"]).copy()
    w["tmax"] = w.groupby("region").tmax.transform(lambda s: s.interpolate(limit_direction="both"))
    daily = daily.merge(hh[["household_id", "persona", "region", "ac_coef"]], on="household_id")
    daily = daily.merge(w[["date", "region", "tmax"]], on=["date", "region"], how="left")
    daily["cdd"] = (daily.tmax - 24).clip(lower=0)            # "degrés de climatisation"
    daily["heatwave"] = (daily.tmax >= 38).astype(int)        # seuil à justifier dans le rapport
    daily["dow"] = daily.date.dt.dayofweek
    daily["is_weekend"] = (daily.dow >= 5).astype(int)
    daily["month"] = daily.date.dt.month
    doy = daily.date.dt.dayofyear
    daily["doy_sin"], daily["doy_cos"] = np.sin(2 * np.pi * doy / 365), np.cos(2 * np.pi * doy / 365)
    daily.drop(columns=["valid_h", "sum_k", "cover"]).to_csv(OUT / "daily.csv", index=False)

    print(f"Relevés lus : {n0:,} | jours foyer : {len(daily):,} | kWh/jour manquants : {daily.kwh_day.isna().mean():.2%}")
    print(f"Jours avec coupure : {(daily.outage_h > 0).mean():.1%} | jours d'anomalie : {daily.anomaly_day.mean():.1%}")
    print(f"-> {OUT / 'daily.csv'}")

if __name__ == "__main__":
    main()