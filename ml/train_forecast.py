"""
ÉnergiTN - Étape 2 ML : prévision de la consommation journalière par foyer (version 2).
Lit  : data/processed/daily.csv  (créé par prepare.py)
Écrit: models/forecast_h{H}.joblib, models/forecast_h{H}_metrics.json,
       data/processed/forecast_h{H}_predictions.csv  (validation + test, avec intervalle q10-q90)

Usage : python train_forecast.py --horizon 1     # prévoir demain
        python train_forecast.py --horizon 7     # prévoir dans 7 jours

Découpage TEMPOREL (jamais aléatoire) :
   entraînement jusqu'au 2025-06-30 | validation 2025-07-01 -> 2026-06-30 (contient un été) | test = été 2026 (juillet-septembre).
Hypothèse : la température du jour prévu est connue (prévision météo). Option --weather-error 2 : simule une prévision
météo imparfaite (±2 °C) pour une évaluation plus réaliste ; l'intervalle de confiance est alors calibré en conséquence.

Améliorations de la version 2 (voir le guide) :
 - modèle HYBRIDE : une droite par foyer (consommation en fonction des degrés de climatisation) + les arbres corrigent le reste.
   Les arbres ne savent pas extrapoler au-delà des températures vues ; la droite, si.
 - intervalle de confiance calibré sur une validation qui contient un ÉTÉ, avec une marge proportionnelle au niveau de consommation.
"""
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
PROC, MODELS = ROOT / "data" / "processed", ROOT / "models"
TRAIN_END, VAL_END = "2025-06-30", "2026-06-30"
BASE = ["tmax", "cdd", "heatwave", "is_holiday", "is_weekend", "dow", "month", "doy_sin", "doy_cos", "ac_coef"]
LAGS = ["lag_h", "lag_h1", "lag_week", "lag_week2", "roll7", "roll30"]
MODS = ("ridge", "rf", "hgb")

def add_lags(d, H):
    d = d.sort_values(["household_id", "date"]).copy()
    g, wk = d.groupby("household_id").kwh_day, 7 * int(np.ceil(H / 7))
    d["lag_h"], d["lag_h1"] = g.shift(H), g.shift(H + 1)
    d["lag_week"], d["lag_week2"] = g.shift(wk), g.shift(wk + 7)       # même jour de semaine, semaine(s) avant
    d["roll7"] = g.transform(lambda s: s.shift(H).rolling(7, min_periods=4).mean())
    d["roll30"] = g.transform(lambda s: s.shift(H).rolling(30, min_periods=15).mean())
    return d

def fit_linear_base(t):
    """Une droite par foyer : kWh/jour = a + b * cdd + c * week-end. Retourne {foyer: (a, b, c)} + coefficients globaux."""
    def ols(x):
        A = np.column_stack([np.ones(len(x)), x.cdd, x.is_weekend])
        return np.linalg.lstsq(A, x.kwh_day.values, rcond=None)[0]
    coefs = {h: ols(x) for h, x in t.groupby("household_id") if len(x) >= 30}
    return coefs, ols(t)

def apply_linear_base(x, coefs, default):
    c = np.array([coefs.get(h, default) for h in x.household_id])
    return c[:, 0] + c[:, 1] * x.cdd.values + c[:, 2] * x.is_weekend.values

def metrics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return {"MAE": round(float(np.mean(np.abs(y - p))), 3),
            "RMSE": round(float(np.sqrt(np.mean((y - p) ** 2))), 3),
            "sMAPE_%": round(float(np.mean(2 * np.abs(y - p) / (np.abs(y) + np.abs(p) + 1e-9)) * 100), 2)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--no-hybrid", action="store_true", help="désactive la droite par foyer (pour comparer)")
    ap.add_argument("--weather-error", type=float, default=0.0,
                    help="erreur de prévision météo simulée, en °C (écart-type), sur validation et test. Ex : 2")
    a = ap.parse_args(); H, HYB = a.horizon, not a.no_hybrid
    MODELS.mkdir(exist_ok=True)
    d = pd.read_csv(PROC / "daily.csv", parse_dates=["date"])
    if a.weather_error > 0:
        # En production on ne connaît PAS la température du jour prévu : on n'a qu'une prévision météo, avec une erreur.
        # On la simule sur validation et test (l'entraînement reste sur les températures observées).
        m_ = d.date > TRAIN_END
        d.loc[m_, "tmax"] = d.loc[m_, "tmax"] + np.random.default_rng(0).normal(0, a.weather_error, int(m_.sum()))
        d["cdd"], d["heatwave"] = (d.tmax - 24).clip(lower=0), (d.tmax >= 38).astype(int)
    d = add_lags(d, H)
    d = pd.concat([d, pd.get_dummies(d[["persona", "region"]], dtype=float)], axis=1)
    feats = BASE + LAGS + [c for c in d.columns if c.startswith(("persona_", "region_"))] + (["lin_base"] if HYB else [])
    d["lin_base"] = 0.0
    d = d.dropna(subset=BASE + LAGS + ["kwh_day"]).copy()
    d["split"] = np.where(d.date <= TRAIN_END, "train", np.where(d.date <= VAL_END, "val", "test"))
    tr, va, te = [d[(d.split == s)] for s in ("train", "val", "test")]
    print(f"Horizon J+{H} | modèle {'hybride' if HYB else 'arbres seuls'} | erreur météo simulée : {a.weather_error:g} °C | lignes train/val/test : {len(tr):,} / {len(va):,} / {len(te):,}")

    mk = {"ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
          "rf": lambda: RandomForestRegressor(n_estimators=120, min_samples_leaf=5, n_jobs=-1, random_state=0),
          "hgb": lambda: HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0)}

    def with_base(x, bundle):
        x = x.copy()
        x["lin_base"] = apply_linear_base(x, *bundle["lin"]) if HYB else 0.0
        return x

    def fit_all(train):
        t = train[train.anomaly_day == 0]
        bundle = {"lin": fit_linear_base(t) if HYB else ({}, np.zeros(3))}
        t = with_base(t, bundle)
        y = t.kwh_day - (t.lin_base if HYB else 0)                       # les arbres apprennent ce que la droite n'explique pas
        for k, f in mk.items():
            bundle[k] = f().fit(t[feats], y)
        for k, q in (("q10", 0.1), ("q90", 0.9)):
            bundle[k] = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=200, random_state=0).fit(t[feats], y)
        return bundle

    def predict(m, x, weights=None, margin=0.0):
        x = with_base(x, m); off = x.lin_base.values if HYB else 0.0
        p = {k: np.clip(m[k].predict(x[feats]) + off, 0, None) for k in MODS}
        w = weights or {k: 1 / len(MODS) for k in MODS}
        ens = sum(w[k] * p[k] for k in MODS)
        lo, hi = np.minimum(m["q10"].predict(x[feats]) + off, ens), np.maximum(m["q90"].predict(x[feats]) + off, ens)
        scale = np.maximum(ens, 1.0)                                      # marge proportionnelle au niveau de consommation
        return p, ens, np.clip(lo - margin * scale, 0, None), hi + margin * scale

    # 1) entraînement sur train -> poids de l'ensemble et marge de l'intervalle choisis sur la validation (qui contient un été)
    m1 = fit_all(tr)
    vn = va[va.anomaly_day == 0]
    pv, _, _, _ = predict(m1, vn)
    mae_val = {k: np.mean(np.abs(vn.kwh_day - pv[k])) for k in MODS}
    inv = {k: 1 / v ** 2 for k, v in mae_val.items()}; weights = {k: v / sum(inv.values()) for k, v in inv.items()}
    _, e_v, lo_v, hi_v = predict(m1, vn, weights)
    scale_v = np.maximum(e_v, 1.0)
    err = np.maximum(lo_v - vn.kwh_day.values, vn.kwh_day.values - hi_v) / scale_v
    margin = float(max(np.quantile(err, 0.8), 0.0))
    # 2) ré-entraînement sur train+val, évaluation sur le test (été 2026)
    m2 = fit_all(pd.concat([tr, va]))
    tn = te[te.anomaly_day == 0]
    p, ens, lo, hi = predict(m2, tn, weights, margin)
    res = {"baseline (même jour sem. dernière)": metrics(tn.kwh_day, tn.lag_week),
           "ridge": metrics(tn.kwh_day, p["ridge"]), "random forest": metrics(tn.kwh_day, p["rf"]),
           "hgb": metrics(tn.kwh_day, p["hgb"]), "ensemble": metrics(tn.kwh_day, ens)}
    cover = float(np.mean((tn.kwh_day >= lo) & (tn.kwh_day <= hi)))
    print(f"\nRésultats sur le TEST (été 2026, {len(tn):,} jours normaux)")
    print(pd.DataFrame(res).T.to_string())
    print(f"Poids ensemble : { {k: round(float(v), 2) for k, v in weights.items()} } | couverture de l'intervalle : {cover:.0%} (cible ~80 %)")

    outs = []
    for x, m, mg in ((va, m1, margin), (te, m2, margin)):
        _, e, l, h = predict(m, x, weights, mg)
        outs.append(x[["household_id", "date", "kwh_day", "anomaly_day", "split"]].assign(pred=e, q10=l, q90=h))
    pd.concat(outs).to_csv(PROC / f"forecast_h{H}_predictions.csv", index=False)
    joblib.dump({"H": H, "features": feats, "models": m2, "weights": weights, "hybrid": HYB, "interval_margin": margin,
                 "trained_until": VAL_END}, MODELS / f"forecast_h{H}.joblib")
    json.dump({"horizon": H, "hybrid": HYB, "weather_error_c": a.weather_error, "test": res, "interval_coverage": cover,
               "weights": {k: float(v) for k, v in weights.items()}, "interval_margin": margin}, open(MODELS / f"forecast_h{H}_metrics.json", "w"), indent=1)
    print(f"-> models/forecast_h{H}.joblib")

if __name__ == "__main__":
    main()