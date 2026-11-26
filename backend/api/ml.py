"""Liaison Django <-> modèles de la chaîne ML (models/forecast_h1.joblib et forecast_h7.joblib).

Ce module reproduit exactement les features de train_forecast.py (lags, moyennes glissantes, météo,
calendrier, indicatrices persona_/region_) puis appelle les modèles sauvegardés :
  * J+1        -> modèle forecast_h1 (lags de la veille, le plus précis)
  * J+2 à J+7  -> modèle forecast_h7 (ses lags sont décalés de 7 jours, donc tous connus : pas de récursion)
L'intervalle q10–q90 utilise les modèles quantiles + la marge de calibration enregistrée dans le .joblib.

Météo du jour prévu : table Weather (observée ou prévision importée par l'admin) ; à défaut, normale
climatique de la région (moyenne des années passées à ±7 jours) : hypothèse affichée dans l'interface.

Détection en direct (UC06) : à chaque relevé saisi/importé, on compare la valeur à la prévision avec la
même règle que anomalies.py (écart > 3 sigma robustes ET > +30 %).
"""
import logging
import math
from datetime import timedelta

import numpy as np
import pandas as pd
from django.conf import settings
from django.db import transaction

from .models import Alert, DailyConsumption, Forecast, Holiday, Household, Weather

log = logging.getLogger("energitn")
FIXED_HOLIDAYS = [(1, 1), (3, 20), (4, 9), (5, 1), (7, 25), (8, 13), (10, 15), (12, 17)]   # comme generate_synthetic.py
HEATWAVE_T = 38          # même seuil que prepare.py
MIN_HISTORY_DAYS = 14    # en dessous : historique insuffisant (UC04, scénario alternatif)
_CACHE = {}


class ModelUnavailable(Exception):
    pass


def model_path(h):
    return settings.ML_MODELS_DIR / f"forecast_h{h}.joblib"


def load_model(h):
    """Charge (et met en cache) un .joblib ; rechargé automatiquement si le fichier change."""
    import joblib
    p = model_path(h)
    if not p.exists():
        raise ModelUnavailable(f"Modèle introuvable : {p}. Lancez train_forecast.py --horizon {h}.")
    mt = p.stat().st_mtime
    if h in _CACHE and _CACHE[h][0] == mt:
        return _CACHE[h][1]
    bundle = joblib.load(p)
    _CACHE[h] = (mt, bundle)
    return bundle


def models_available():
    return all(model_path(h).exists() for h in (1, 7))


# --------------------------------------------------------------------------- météo et calendrier
def weather_for(region, dates):
    """{date: (tmax, source)} ; source = observee | prevision | climatologie."""
    dates = list(dates)
    found = {w["date"]: (w["tmax"], w["source"]) for w in
             Weather.objects.filter(region=region, date__in=dates).values("date", "tmax", "source")}
    missing = [d for d in dates if d not in found]
    if missing:
        hist = list(Weather.objects.filter(region=region).values_list("date", "tmax"))
        for d in missing:
            doy = d.timetuple().tm_yday
            near = [t for (hd, t) in hist if min(abs(hd.timetuple().tm_yday - doy), 365 - abs(hd.timetuple().tm_yday - doy)) <= 7]
            found[d] = (round(sum(near) / len(near), 1) if near else 25.0, "climatologie")
    return found


def holidays_between(d0, d1):
    days = set(Holiday.objects.filter(date__range=(d0, d1)).values_list("date", flat=True))
    for y in range(d0.year, d1.year + 1):
        for m, dd in FIXED_HOLIDAYS:
            try:
                from datetime import date as _d
                x = _d(y, m, dd)
            except ValueError:
                continue
            if d0 <= x <= d1:
                days.add(x)
    return days


# --------------------------------------------------------------------------- features
def _history(h, until=None, days=75):
    qs = DailyConsumption.objects.filter(household=h)
    if until:
        qs = qs.filter(date__lte=until)
    rows = list(qs.order_by("-date").values_list("date", "kwh")[:days])
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(d): k for d, k in rows}).sort_index()
    return s.asfreq("D")        # jours manquants -> NaN


def _features(h, hist, targets, H, bundle):
    feats = bundle["features"]
    wx = weather_for(h.region, [t.date() for t in targets])
    hol = holidays_between(targets[0].date(), targets[-1].date())
    wk = 7 * int(math.ceil(H / 7))
    mean_all = float(hist.mean()) if hist.notna().any() else 0.0
    rows, meta = [], []
    for t in targets:
        def at(k):
            return hist.get(t - pd.Timedelta(days=k), np.nan)

        def win(a, n, mn):
            w = hist.loc[t - pd.Timedelta(days=a + n - 1): t - pd.Timedelta(days=a)]
            return float(w.mean()) if w.notna().sum() >= mn else np.nan
        tmax, src = wx[t.date()]
        doy = t.dayofyear
        r = {"tmax": tmax, "cdd": max(tmax - 24, 0.0), "heatwave": int(tmax >= HEATWAVE_T),
             "is_holiday": int(t.date() in hol), "is_weekend": int(t.dayofweek >= 5), "dow": t.dayofweek,
             "month": t.month, "doy_sin": np.sin(2 * np.pi * doy / 365), "doy_cos": np.cos(2 * np.pi * doy / 365),
             "ac_coef": h.ac_coef, "lag_h": at(H), "lag_h1": at(H + 1), "lag_week": at(wk), "lag_week2": at(wk + 7),
             "roll7": win(H, 7, 4), "roll30": win(H, 30, 15)}
        # valeurs manquantes (trou de relevé) : repli prudent sur les moyennes, puis sur la moyenne du foyer
        r["roll30"] = r["roll30"] if not np.isnan(r["roll30"]) else (r["roll7"] if not np.isnan(r["roll7"]) else mean_all)
        r["roll7"] = r["roll7"] if not np.isnan(r["roll7"]) else r["roll30"]
        for k in ("lag_h", "lag_h1", "lag_week", "lag_week2"):
            if np.isnan(r[k]):
                r[k] = r["roll7"]
        rows.append(r)
        meta.append((tmax, src))
    X = pd.DataFrame(rows)
    for f in feats:
        if f.startswith(("persona_", "region_")):
            X[f] = 0.0
    if f"persona_{h.persona}" in feats:
        X[f"persona_{h.persona}"] = 1.0
    if f"region_{h.region}" in feats:
        X[f"region_{h.region}"] = 1.0
    X = apply_linear_base(bundle, h, X)
    return X[feats].astype(float), meta


def apply_linear_base(bundle, h, X):
    """Modèle HYBRIDE (train_forecast.py v2) : une droite par foyer kWh = a + b·cdd + c·week-end,
    apprise à l'entraînement et stockée dans bundle["models"]["lin"] = ({foyer: (a, b, c)}, (a, b, c) global).
    Elle sert de variable « lin_base » ET de base à laquelle on ajoute la sortie des arbres (voir _predict).
    Un foyer inconnu à l'entraînement (vrai foyer inscrit) utilise les coefficients globaux."""
    if "lin_base" not in bundle["features"]:
        return X
    if not bundle.get("hybrid", False):
        X["lin_base"] = 0.0
        return X
    coefs, default = bundle["models"]["lin"]
    a, b, c = (float(v) for v in coefs.get(h.household_id, default))
    X["lin_base"] = a + b * X["cdd"].astype(float) + c * X["is_weekend"].astype(float)
    return X


def _predict(bundle, X):
    m, w = bundle["models"], bundle["weights"]
    mg = float(bundle.get("interval_margin", 0.0))
    if bundle.get("hybrid", False):
        # identique à predict() de train_forecast.py v2 : arbres + droite du foyer, marge × max(prévision, 1)
        off = X["lin_base"].values
        ens = sum(w[k] * np.clip(m[k].predict(X) + off, 0, None) for k in w)
        scale = np.maximum(ens, 1.0)
        lo = np.clip(np.minimum(m["q10"].predict(X) + off, ens) - mg * scale, 0, None)
        hi = np.maximum(m["q90"].predict(X) + off, ens) + mg * scale
        return ens, lo, hi
    ens = np.clip(sum(w[k] * m[k].predict(X) for k in w), 0, None)
    lo = np.minimum(m["q10"].predict(X), ens)
    hi = np.maximum(m["q90"].predict(X), ens)
    if bundle.get("interval_margin_kind") == "relative":
        lo, hi = lo - mg * ens, hi + mg * ens
    else:
        lo, hi = lo - mg, hi + mg
    return ens, np.clip(lo, 0, None), hi


# --------------------------------------------------------------------------- API publique
def forecast_household(h, days=7):
    """Calcule et enregistre les prévisions des `days` jours qui suivent le dernier relevé du foyer.
    Retourne le nombre de prévisions écrites (0 si historique insuffisant)."""
    hist = _history(h)
    if hist.notna().sum() < MIN_HISTORY_DAYS:
        Forecast.objects.filter(household=h, kind="future").delete()
        return 0
    last = hist.last_valid_index()
    targets = [last + pd.Timedelta(days=k) for k in range(1, days + 1)]
    out = []
    b1 = load_model(1)
    X, meta = _features(h, hist, targets[:1], 1, b1)
    p, lo, hi = _predict(b1, X)
    out.append((targets[0], 1, "forecast_h1", p[0], lo[0], hi[0], *meta[0]))
    if days > 1:
        b7 = load_model(7)
        X, meta = _features(h, hist, targets[1:], 7, b7)
        p, lo, hi = _predict(b7, X)
        for i, t in enumerate(targets[1:]):
            out.append((t, i + 2, "forecast_h7", p[i], lo[i], hi[i], *meta[i]))
    with transaction.atomic():
        Forecast.objects.filter(household=h, kind="future").delete()
        Forecast.objects.bulk_create([Forecast(
            household=h, target_date=t.date(), horizon_days=hz, kind="future", model_name=name,
            predicted_kwh=round(float(pv), 3), q10=round(float(l), 3), q90=round(float(u), 3),
            tmax_used=tm, weather_source=src) for (t, hz, name, pv, l, u, tm, src) in out])
    return len(out)


def run_inference(households=None, stdout=None):
    """Tâche « nocturne » du guide : recalcule les prévisions de tous les foyers."""
    if not models_available():
        raise ModelUnavailable("Fichiers forecast_h1.joblib / forecast_h7.joblib absents du dossier models/.")
    hs = households if households is not None else Household.objects.all()
    n_h = n_f = skipped = 0
    for h in hs:
        k = forecast_household(h)
        n_h += 1
        n_f += k
        skipped += k == 0
    msg = f"Inférence : {n_f} prévisions pour {n_h - skipped} foyers ({skipped} sans historique suffisant)."
    if stdout:
        stdout.write(msg)
    else:
        log.info(msg)
    return {"households": n_h, "forecasts": n_f, "skipped": skipped}


def predict_for_date(h, d):
    """Prévision J+1 d'un jour donné à partir de l'historique strictement antérieur (pour la détection)."""
    hist = _history(h, until=d - timedelta(days=1))
    if hist.notna().sum() < MIN_HISTORY_DAYS:
        return None
    b1 = load_model(1)
    X, _ = _features(h, hist, [pd.Timestamp(d)], 1, b1)
    p, lo, hi = _predict(b1, X)
    return float(p[0]), float(lo[0]), float(hi[0])


def household_sigma(h):
    """Écart-type ROBUSTE (MAD) des résidus de prévision du foyer, comme anomalies.py."""
    res = [a - p for a, p in Forecast.objects.filter(household=h, kind="backtest", actual_kwh__isnull=False)
           .values_list("actual_kwh", "predicted_kwh")]
    if len(res) < 20:
        return None
    r = np.asarray(res)
    return max(float(np.median(np.abs(r - np.median(r))) * 1.4826), 0.05)


def check_reading(h, d, kwh):
    """UC06 : compare un nouveau relevé à la prévision ; crée une alerte si l'écart est significatif."""
    try:
        pred = predict_for_date(h, d)
    except ModelUnavailable:
        return None
    if not pred:
        return None
    p, lo, hi = pred
    sigma = household_sigma(h) or max(0.1 * p, 0.3)
    ratio, z = kwh / max(p, 0.5), (kwh - p) / sigma
    Alert.objects.filter(household=h, date=d, source="live").delete()
    if z > 3 and ratio > 1.3:
        typ, sev = "surconsommation", ("haute" if ratio > 2 else "moyenne")
    elif kwh > hi and ratio > 1.15:
        typ, sev = "ecart_prevision", "basse"
    else:
        return None
    a, _ = Alert.objects.update_or_create(household=h, date=d, anomaly_type=typ, defaults={
        "severity": sev, "kwh": round(kwh, 2), "expected_kwh": round(p, 2), "ratio": round(ratio, 2),
        "source": "live", "is_resolved": False,
        "description": f"Relevé de {kwh:.1f} kWh pour {p:.1f} kWh prévus (intervalle {lo:.1f}–{hi:.1f})."})
    return a


def save_readings(h, items, source="saisie"):
    """Enregistre des relevés journaliers [(date, kwh)], déclenche la détection puis recalcule les prévisions."""
    items = sorted(items)
    wx = weather_for(h.region, [d for d, _ in items]) if items else {}
    alerts = []
    for d, k in items:
        DailyConsumption.objects.update_or_create(household=h, date=d, defaults={
            "kwh": round(float(k), 3), "tmax": wx.get(d, (None,))[0], "source": source})
    for d, k in items:
        a = check_reading(h, d, float(k))
        if a:
            alerts.append(a)
    n = 0
    try:
        n = forecast_household(h)
    except ModelUnavailable as e:
        log.warning(str(e))
    return {"saved": len(items), "alerts": alerts, "forecasts": n}
