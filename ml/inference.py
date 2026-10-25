"""
ÉnergiTN - Inférence : prévoir les prochains jours avec le modèle sauvegardé (utilisé par Django).

Charge models/forecast_h1.joblib (créé par train_forecast.py --horizon 1) et prédit J+1, J+2, ... J+n
par RÉCURRENCE : la prévision de J+1 sert de "consommation passée" pour prévoir J+2, etc.
Les températures des jours à prévoir doivent être connues (prévision météo, ou fichier météo en démo).
"""
from pathlib import Path
import numpy as np, pandas as pd, joblib

def load_bundle(path):
    return joblib.load(Path(path))

def forecast_next_days(history, weather, holidays, bundle, days=7):
    """
    history  : DataFrame [household_id, date (Timestamp), kwh_day, region, persona, ac_coef] - le PASSÉ uniquement
    weather  : DataFrame [date (Timestamp), region, tmax] - températures des jours à prédire
    holidays : ensemble de Timestamp (jours fériés)
    Retourne : DataFrame [household_id, date, horizon, predicted, low, high]  (horizon = nombre de jours d'avance)
    """
    feats, m, w, margin = bundle["features"], bundle["models"], bundle["weights"], bundle["interval_margin"]
    hyb = bundle.get("hybrid", False)
    coefs, default = m["lin"]
    holidays = {pd.Timestamp(x) for x in holidays}

    series, meta = {}, {}
    for hid, g in history.groupby("household_id"):
        g = g.sort_values("date")
        s = g.set_index("date").kwh_day.astype(float)
        series[hid] = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
        meta[hid] = g.iloc[-1]
    wx = {r: d.set_index("date").tmax for r, d in weather.groupby("region")}

    out = []
    for step in range(1, days + 1):
        rows, keys = [], []
        for hid, s in series.items():
            t, mt = s.index.max() + pd.Timedelta(days=1), meta[hid]
            tmax = wx.get(mt.region, pd.Series(dtype=float)).get(t, np.nan)
            if pd.isna(tmax):
                continue                                           # pas de météo pour ce jour : on s'arrête pour ce foyer
            lag = lambda k: s.get(t - pd.Timedelta(days=k), np.nan)
            win7 = s.reindex(pd.date_range(t - pd.Timedelta(days=7), t - pd.Timedelta(days=1)))
            win30 = s.reindex(pd.date_range(t - pd.Timedelta(days=30), t - pd.Timedelta(days=1)))
            roll7 = win7.mean() if win7.count() >= 4 else np.nan
            roll30 = win30.mean() if win30.count() >= 15 else np.nan
            fill = roll30 if not pd.isna(roll30) else roll7
            lags = {k: (v if not pd.isna(v) else fill) for k, v in
                    (("lag_h", lag(1)), ("lag_h1", lag(2)), ("lag_week", lag(7)), ("lag_week2", lag(14)))}
            if pd.isna(fill) or any(pd.isna(v) for v in lags.values()):
                continue                                           # historique insuffisant
            cdd, wk = max(tmax - 24, 0.0), int(t.dayofweek >= 5)
            row = {f: 0.0 for f in feats}
            row.update(tmax=tmax, cdd=cdd, heatwave=int(tmax >= 38), is_holiday=int(t in holidays), is_weekend=wk,
                       dow=t.dayofweek, month=t.month, doy_sin=np.sin(2 * np.pi * t.dayofyear / 365),
                       doy_cos=np.cos(2 * np.pi * t.dayofyear / 365), ac_coef=float(mt.ac_coef),
                       roll7=roll7 if not pd.isna(roll7) else fill, roll30=fill, **lags)
            for key in (f"persona_{mt.persona}", f"region_{mt.region}"):
                if key in row:
                    row[key] = 1.0
            c = coefs.get(hid, default)
            row["_lin"] = (c[0] + c[1] * cdd + c[2] * wk) if hyb else 0.0
            if "lin_base" in row:
                row["lin_base"] = row["_lin"]
            rows.append(row); keys.append((hid, t))
        if not rows:
            break
        X = pd.DataFrame(rows)
        lin = X.pop("_lin").values
        X = X[feats]
        p = {k: np.clip(m[k].predict(X) + lin, 0, None) for k in ("ridge", "rf", "hgb")}
        ens = sum(w[k] * p[k] for k in ("ridge", "rf", "hgb"))
        scale = np.maximum(ens, 1.0)
        lo = np.clip(np.minimum(m["q10"].predict(X) + lin, ens) - margin * scale, 0, None)
        hi = np.maximum(m["q90"].predict(X) + lin, ens) + margin * scale
        for (hid, t), e, l, h in zip(keys, ens, lo, hi):
            series[hid].loc[t] = e                                  # la prévision devient le "passé" du jour suivant
            out.append(dict(household_id=hid, date=t, horizon=step, predicted=float(e), low=float(l), high=float(h)))
    return pd.DataFrame(out)
