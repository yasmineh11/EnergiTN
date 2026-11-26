"""Fonctions « innovantes » appuyées directement sur les modèles .joblib de la chaîne ML.

* forecast_scenario : jumeau numérique du foyer — on relance les VRAIS modèles J+1/J+7 en ajoutant
  +x °C à la météo prévue (scénario de canicule) et on compare kWh et facture. Pas de règle linéaire :
  c'est le modèle entraîné qui répond.
* ml_health        : état de la liaison Django <-> ML (fichiers .joblib, version scikit-learn,
  fraîcheur de l'inférence, foyers sans prévision).
* drift_report     : surveillance de la dérive (BF15) — MAPE glissante sur 30 jours comparée à la MAPE
  de référence du jeu de test enregistrée dans *_metrics.json.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from django.db.models import Max
from django.utils import timezone

from . import billing, ml
from .facts import model_quality
from .models import Alert, DailyConsumption, Forecast, Household


def forecast_scenario(h, delta_t=4.0, days=7):
    """Prévisions de base et prévisions « canicule » (+delta_t °C sur la tmax de chaque jour)."""
    hist = ml._history(h)
    if hist.notna().sum() < ml.MIN_HISTORY_DAYS:
        return None
    last = hist.last_valid_index()
    targets = [last + pd.Timedelta(days=k) for k in range(1, days + 1)]
    out = []
    for H, tg in ((1, targets[:1]), (7, targets[1:])):
        if not tg:
            continue
        b = ml.load_model(H)
        X, meta = ml._features(h, hist, tg, H, b)
        base, lo, hi = ml._predict(b, X)
        Xs = X.copy()
        Xs["tmax"] = Xs["tmax"] + delta_t
        Xs["cdd"] = np.maximum(Xs["tmax"] - 24, 0.0)
        Xs["heatwave"] = (Xs["tmax"] >= ml.HEATWAVE_T).astype(float)
        Xs = ml.apply_linear_base(b, h, Xs)[X.columns]      # modèle hybride : la droite du foyer suit la chaleur
        sc, slo, shi = ml._predict(b, Xs)
        for i, t in enumerate(tg):
            out.append({"date": t.date().isoformat(), "tmax": round(meta[i][0], 1), "tmax_sc": round(meta[i][0] + delta_t, 1),
                        "base": round(float(base[i]), 2), "scenario": round(float(sc[i]), 2),
                        "sc_q10": round(float(slo[i]), 2), "sc_q90": round(float(shi[i]), 2)})
    b_tot = sum(x["base"] for x in out)
    s_tot = sum(x["scenario"] for x in out)
    # effet sur un mois : même écart relatif appliqué à la projection mensuelle
    month_kwh = b_tot / len(out) * 30
    bill_b = billing.estimate(month_kwh, 30)
    bill_s = billing.estimate(month_kwh * (s_tot / b_tot if b_tot else 1), 30)
    return {"delta_t": delta_t, "days": out, "base_kwh": round(b_tot, 1), "scenario_kwh": round(s_tot, 1),
            "extra_pct": round((s_tot / b_tot - 1) * 100, 1) if b_tot else None,
            "bill_base": bill_b["total"], "bill_scenario": bill_s["total"],
            "band_change": bill_s["band"] != bill_b["band"], "band_label": bill_s["band_label"],
            "ac_coef": h.ac_coef}


def ml_health():
    files = []
    for H in (1, 7):
        p = ml.model_path(H)
        info = {"name": p.name, "exists": p.exists()}
        if p.exists():
            st = p.stat()
            info.update({"size_mb": round(st.st_size / 1e6, 1),
                         "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone()).isoformat()})
            try:
                b = ml.load_model(H)
                info.update({"loaded": True, "n_features": len(b.get("features", [])),
                             "members": sorted(k for k in b.get("models", {}))})
            except Exception as e:      # noqa: BLE001 — on affiche l'erreur dans l'interface
                info.update({"loaded": False, "error": str(e)[:200]})
        files.append(info)
    try:
        import sklearn
        sk_runtime = sklearn.__version__
    except ImportError:
        sk_runtime = None
    sk_trained = (model_quality().get("forecast_h1") or {}).get("sklearn")
    last_inf = Forecast.objects.filter(kind="future").aggregate(m=Max("generated_at"))["m"]
    n_h = Household.objects.count()
    with_fc = Forecast.objects.filter(kind="future").values("household").distinct().count()
    last_data = DailyConsumption.objects.aggregate(m=Max("date"))["m"]
    checks = [
        {"k": "files", "ok": all(f["exists"] and f.get("loaded") for f in files)},
        {"k": "sklearn", "ok": bool(sk_trained and sk_runtime and sk_trained == sk_runtime), "a": sk_trained, "b": sk_runtime},
        {"k": "coverage", "ok": n_h > 0 and with_fc == n_h, "a": with_fc, "b": n_h},
        {"k": "fresh", "ok": bool(last_inf and timezone.now() - last_inf < timedelta(days=2))},
    ]
    return {"files": files, "sklearn_trained": sk_trained, "sklearn_runtime": sk_runtime,
            "last_inference": timezone.localtime(last_inf).isoformat() if last_inf else None,
            "households": n_h, "with_forecast": with_fc,
            "data_until": last_data.isoformat() if last_data else None,
            "checks": checks, "score": sum(c["ok"] for c in checks), "total": len(checks)}


def drift_report(window=30):
    """MAPE glissante (fenêtre de `window` jours) des prévisions J+1 évaluées, comparée à la référence du test."""
    rows = list(Forecast.objects.filter(kind="backtest", horizon_days=1, actual_kwh__gt=0.5)
                .values_list("household_id", "target_date", "predicted_kwh", "actual_kwh"))
    if not rows:
        return None
    # comme la référence (test sur jours normaux) : on écarte les jours signalés comme anomalies
    flagged = set(Alert.objects.values_list("household_id", "date"))
    rows = [(d, p, a) for hid, d, p, a in rows if (hid, d) not in flagged]
    df = pd.DataFrame(rows, columns=["d", "p", "a"])
    df["ape"] = (df["a"] - df["p"]).abs() / df["a"]
    daily = df.groupby("d")["ape"].mean().sort_index() * 100
    roll = daily.rolling(window, min_periods=max(7, window // 3)).mean().dropna()
    ref = ((model_quality().get("forecast_h1") or {}).get("test", {}).get("ensemble") or {}).get("MAPE_%")
    cur = float(roll.iloc[-1]) if len(roll) else None
    ratio = cur / ref if (cur and ref) else None
    status = None if ratio is None else ("ok" if ratio < 1.25 else "watch" if ratio < 1.6 else "drift")
    step = max(1, len(roll) // 120)
    return {"window": window, "reference_mape": ref, "current_mape": round(cur, 2) if cur else None,
            "ratio": round(ratio, 2) if ratio else None, "status": status,
            "series": [{"date": d.isoformat(), "mape": round(float(v), 2)} for d, v in roll.iloc[::step].items()],
            "worst_day": {"date": daily.idxmax().isoformat(), "mape": round(float(daily.max()), 1)}}
