"""
ÉnergiTN - Étape 4 ML : détection d'anomalies de consommation (au niveau du jour).
Lit  : data/processed/daily.csv, data/processed/forecast_h1_predictions.csv (créé par train_forecast.py --horizon 1)
Écrit: data/processed/anomalies_flagged.csv, models/anomaly_metrics.json

Trois détecteurs complémentaires :
  1. RÉSIDU : consommation réelle bien au-dessus de la prévision (écart > 3 sigma du foyer ET > +30 %).
  2. NUIT   : consommation de 0h-5h très supérieure à l'habitude du foyer (x1,8).
  3. ISOLATION FOREST : jour atypique sur (ratio réel/prévu, écart normalisé, ratio de nuit).
La colonne anomaly_day (vérité terrain) ne sert QU'À MESURER la qualité, jamais à décider.
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parent.parent
PROC, MODELS = ROOT / "data" / "processed", ROOT / "models"

def prf(y, p):
    tp, fp, fn = int(((y == 1) & (p == 1)).sum()), int(((y == 0) & (p == 1)).sum()), int(((y == 1) & (p == 0)).sum())
    pr, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"precision": round(pr, 2), "rappel": round(rc, 2), "F1": round(2 * pr * rc / max(pr + rc, 1e-9), 2), "tp": tp, "fp": fp, "fn": fn}

def main():
    MODELS.mkdir(exist_ok=True)
    d = pd.read_csv(PROC / "daily.csv", parse_dates=["date"])[["household_id", "date", "night_mean", "outage_h"]]
    f = pd.read_csv(PROC / "forecast_h1_predictions.csv", parse_dates=["date"])
    x = f.merge(d, on=["household_id", "date"]).sort_values(["household_id", "date"])
    x["ratio"] = x.kwh_day / x.pred.clip(lower=0.5)
    x["resid"] = x.kwh_day - x.pred
    sigma = x[(x.split == "val") & (x.anomaly_day == 0)].groupby("household_id").resid.std().rename("sigma")
    x = x.merge(sigma, on="household_id")
    x["z"] = x.resid / x.sigma
    ref = x.groupby("household_id").night_mean.transform(lambda s: s.shift(1).rolling(30, min_periods=10).median())
    x["night_ratio"] = x.night_mean / ref
    x = x.dropna(subset=["z", "night_ratio"]).copy()

    val, test = x[x.split == "val"], x[x.split == "test"].copy()
    test["rule_resid"] = ((test.z > 3) & (test.ratio > 1.3)).astype(int)
    test["rule_night"] = (test.night_ratio > 1.8).astype(int)
    cols = ["ratio", "z", "night_ratio"]
    iso = IsolationForest(n_estimators=200, contamination=0.04, random_state=0).fit(val[val.anomaly_day == 0][cols])
    test["iso"] = (iso.predict(test[cols]) == -1).astype(int)
    test["combined"] = ((test.rule_resid == 1) | (test.rule_night == 1)).astype(int)
    test["combined_iso"] = ((test.combined == 1) | ((test.iso == 1) & (test.ratio > 1.15))).astype(int)

    names = {"rule_resid": "règle : résidu de prévision", "rule_night": "règle : conso nocturne", "iso": "Isolation Forest seule",
             "combined": "règles combinées (résidu OU nuit)", "combined_iso": "règles + Isolation Forest"}
    res = {names[k]: prf(test.anomaly_day, test[k]) for k in names}
    print(f"Évaluation sur le TEST (été 2026) : {len(test):,} jours foyer, {int(test.anomaly_day.sum())} jours réellement anormaux")
    print(pd.DataFrame(res).T.to_string())

    flagged = test[test.combined == 1].copy()
    flagged["type"] = np.where(flagged.rule_resid == 1, "surconsommation", "consommation_nocturne")
    flagged["gravite"] = np.where(flagged.ratio > 2.0, "haute", "moyenne")
    flagged[["household_id", "date", "kwh_day", "pred", "ratio", "night_ratio", "type", "gravite", "anomaly_day"]].to_csv(PROC / "anomalies_flagged.csv", index=False)
    with open(MODELS / "anomaly_metrics.json", "w", encoding="utf-8") as fh:      # utf-8 explicite (Windows écrit en cp1252 sinon)
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"\n{len(flagged)} jours signalés -> {PROC / 'anomalies_flagged.csv'}")
    fp = test[(test.combined == 1) & (test.anomaly_day == 0)]
    print(f"Fausses alertes : {len(fp)} ; dont jours de coupure (reprise de courant) : {int((fp.outage_h > 0).sum())}")

if __name__ == "__main__":
    main()