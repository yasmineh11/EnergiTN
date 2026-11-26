"""Construit les données JSON des trois espaces (injectées dans les pages et exposées par l'API REST)."""
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import TruncMonth

from . import billing
from .facts import TIPS, household_facts, model_quality
from .models import (Alert, ChatMessage, DailyConsumption, Forecast, Holiday, Household, HouseholdProfile, ModelRun,
                     Outage, PipelineRun, TariffBand, UserProfile, Weather)
from .regions import BY_ID, REGIONS, region_of


def role_of(user):
    if not user.is_authenticated:
        return None
    p = getattr(user, "profile", None)
    if p:
        return p.role
    return "admin" if user.is_superuser else None


def _r(x, n=2):
    return None if x is None else round(float(x), n)


# =========================================================================== FOYER
def foyer_dashboard(h):
    f = household_facts(h)
    if not f.get("has_data"):
        return {"facts": f}
    flagged = set(Alert.objects.filter(household=h).values_list("date", flat=True))
    rows = list(DailyConsumption.objects.filter(household=h).order_by("-date").values("date", "kwh", "tmax")[:400])[::-1]
    days = [{"date": r["date"].isoformat(), "kwh": _r(r["kwh"]), "tmax": _r(r["tmax"], 1), "anomaly": r["date"] in flagged} for r in rows]
    months = list(DailyConsumption.objects.filter(household=h).annotate(m=TruncMonth("date")).values("m")
                  .annotate(kwh=Sum("kwh"), n=Count("id")).order_by("-m")[:12])[::-1]
    bt = list(Forecast.objects.filter(household=h, kind="backtest", horizon_days=1, actual_kwh__isnull=False)
              .order_by("-target_date").values("target_date", "predicted_kwh", "actual_kwh", "q10", "q90")[:21])[::-1]
    prof = getattr(h, "profile", None)
    return {
        "facts": f, "days": days,
        "months": [{"month": m["m"].strftime("%Y-%m"), "kwh": _r(m["kwh"], 1), "days": m["n"]} for m in months],
        "backtest": [{"date": b["target_date"].isoformat(), "pred": _r(b["predicted_kwh"]), "actual": _r(b["actual_kwh"]),
                      "q10": _r(b["q10"]), "q90": _r(b["q90"])} for b in bt],
        "hourly": prof.hourly if prof else {},
    }


def foyer_readings(h, n=60):
    rows = list(DailyConsumption.objects.filter(household=h).order_by("-date")[:n])
    alerts = {(a.date): a.severity for a in Alert.objects.filter(household=h)}
    return {"rows": [{"date": r.date.isoformat(), "kwh": _r(r.kwh), "tmax": _r(r.tmax, 1), "source": r.source,
                      "alert": alerts.get(r.date)} for r in rows],
            "last": rows[0].date.isoformat() if rows else None,
            "count": DailyConsumption.objects.filter(household=h).count()}


def foyer_alerts(h):
    return [{"id": a.id, "date": a.date.isoformat(), "type": a.anomaly_type, "severity": a.severity, "kwh": _r(a.kwh),
             "expected": _r(a.expected_kwh), "ratio": _r(a.ratio), "night_ratio": _r(a.night_ratio), "source": a.source,
             "resolved": a.is_resolved} for a in Alert.objects.filter(household=h).order_by("-date")[:40]]


def chat_history(user, n=40):
    return [{"role": m.role, "content": m.content, "engine": m.engine, "at": m.created_at.isoformat()}
            for m in ChatMessage.objects.filter(user=user).order_by("-created_at")[:n]][::-1]


# =========================================================================== ANALYSTE
def _season_key(d):
    return "summer" if d.month in (6, 7, 8, 9) else "winter" if d.month in (12, 1, 2) else "all"


def _households_by_region():
    out = defaultdict(list)
    for h in Household.objects.select_related("profile"):
        if h.region_id:
            out[h.region_id].append(h)
    return out


def analyst_forecast():
    """UC17 : demande prévue par région (prévisions futures des modèles .joblib)."""
    fut = Forecast.objects.filter(kind="future")
    cnt = Counter(fut.values_list("target_date", flat=True))
    if not cnt:
        return None
    dates = sorted(d for d, _ in cnt.most_common(7))
    byreg = _households_by_region()
    regions, nat = [], [0.0] * len(dates)
    for reg in REGIONS:
        hs = byreg.get(reg["id"], [])
        ids = [h.id for h in hs]
        if not ids:
            continue
        fm = {r["target_date"]: r for r in fut.filter(household_id__in=ids, target_date__in=dates).values("target_date")
              .annotate(m=Avg("predicted_kwh"), s=Sum("predicted_kwh"), lo=Sum("q10"), hi=Sum("q90"), t=Avg("tmax_used"))}
        hist = DailyConsumption.objects.filter(household_id__in=ids)
        daily_mean = list(hist.values("date").annotate(m=Avg("kwh")).values_list("m", flat=True))
        daily_mean.sort()
        record = daily_mean[int(len(daily_mean) * 0.99) - 1] if daily_mean else None    # P99 historique (kWh/foyer/jour)
        season = _season_key(dates[0])
        shape = [0.0] * 24
        nshape = 0
        for h in hs:
            hp = getattr(h, "profile", None)
            s = (hp.hourly or {}).get(season) or (hp.hourly or {}).get("all") if hp else None
            if s:
                tot = sum(s) or 1
                shape = [a + b / tot * 24 for a, b in zip(shape, s)]
                nshape += 1
        shape = [round(x / nshape, 4) for x in shape] if nshape else [1.0] * 24
        heat = HouseholdProfile.objects.filter(household_id__in=ids).aggregate(s=Avg("heat_sens"), m=Avg("mean_day"))
        out = {**{k: reg[k] for k in ("id", "fr", "ar", "cap", "x", "y")}, "households": len(ids),
               "record": _r(record), "heat_sens": _r(heat["s"], 3), "mean_day": _r(heat["m"]), "shape": shape,
               "pred": [_r(fm[d]["m"]) if d in fm else None for d in dates],
               "total": [_r(fm[d]["s"], 1) if d in fm else None for d in dates],
               "lo": [_r(fm[d]["lo"], 1) if d in fm else None for d in dates],
               "hi": [_r(fm[d]["hi"], 1) if d in fm else None for d in dates],
               "tmax": [_r(fm[d]["t"], 1) if d in fm else None for d in dates]}
        out["load"] = [_r(p / record, 3) if p and record else None for p in out["pred"]]
        for i, v in enumerate(out["total"]):
            nat[i] += v or 0
        regions.append(out)
    # historique mensuel par région (kWh moyen par foyer et par jour)
    hist = defaultdict(dict)
    for r in (DailyConsumption.objects.annotate(m=TruncMonth("date")).values("m", "household__region").annotate(a=Avg("kwh"))):
        reg = region_of(r["household__region"])
        if reg:
            hist[reg["id"]][r["m"].strftime("%Y-%m")] = _r(r["a"])
    months = sorted({m for v in hist.values() for m in v})[-18:]
    wsrc = Counter(fut.filter(target_date__in=dates).values_list("weather_source", flat=True)).most_common(1)
    q = model_quality().get("forecast_h1", {})
    return {"dates": [d.isoformat() for d in dates], "regions": regions, "national": [round(x, 1) for x in nat],
            "history": {"months": months, "series": {k: [v.get(m) for m in months] for k, v in hist.items()}},
            "weather_source": wsrc[0][0] if wsrc else "", "data_until": (dates[0] - timedelta(days=1)).isoformat(),
            "mape": (q.get("test", {}).get("ensemble") or {}).get("MAPE_%"),
            "baseline": (q.get("test", {}).get("baseline (même jour sem. dernière)") or {}).get("MAPE_%")}


def analyst_profiles():
    """UC18 : répartition des profils (K-Means) par région, et caractéristiques de chaque profil."""
    profs = list(HouseholdProfile.objects.select_related("household"))
    clusters = {}
    for p in profs:
        c = clusters.setdefault(p.cluster, {"cluster": p.cluster, "name": p.profil, "n": 0, "regions": Counter(), "rows": []})
        c["n"] += 1
        rid = p.household.region_id
        if rid:
            c["regions"][rid] += 1
        c["rows"].append(p)
    out = []
    feats = ["mean_day", "evening_share", "night_share", "summer_ratio", "load_factor", "heat_sens", "weekend_ratio"]
    for c in sorted(clusters.values(), key=lambda x: x["cluster"]):
        avg = {f: _r(sum(getattr(p, f) or 0 for p in c["rows"]) / len(c["rows"])) for f in feats}
        hours = [0.0] * 24
        for p in c["rows"]:
            s = (p.hourly or {}).get("all")
            if s:
                hours = [a + b for a, b in zip(hours, s)]
        n_al = Alert.objects.filter(household__in=[p.household for p in c["rows"]]).count()
        out.append({"cluster": c["cluster"], "name": c["name"], "n": c["n"], "features": avg,
                    "regions": dict(c["regions"]), "hourly": [_r(x / len(c["rows"]), 3) for x in hours], "alerts": n_al,
                    "alerts_per_household": _r(n_al / c["n"], 1)})
    # bornes globales pour normaliser les jauges
    bounds = {f: [_r(min(getattr(p, f) or 0 for p in profs)), _r(max(getattr(p, f) or 0 for p in profs))] for f in feats} if profs else {}
    return {"clusters": out, "bounds": bounds,
            "regions": [{k: r[k] for k in ("id", "fr", "ar")} for r in REGIONS],
            "silhouette": (model_quality().get("profiles") or {}).get("silhouette"),
            "ari": (model_quality().get("profiles") or {}).get("ari_vs_personas")}


def analyst_anomalies():
    """UC19 : anomalies récurrentes par région, par type, par profil ; foyers à surveiller ; coupures et canicule."""
    alerts = list(Alert.objects.select_related("household", "household__profile"))
    by_reg = defaultdict(lambda: Counter())
    by_month = defaultdict(lambda: Counter())
    by_hh = defaultdict(list)
    for a in alerts:
        rid = a.household.region_id if a.household else None
        if rid:
            by_reg[rid][a.anomaly_type] += 1
        by_month[a.date.strftime("%Y-%m")][a.anomaly_type] += 1
        if a.household:
            by_hh[a.household].append(a)
    watch = []
    for h, al in by_hh.items():
        if len(al) >= 2:
            p = getattr(h, "profile", None)
            reg = h.region_info or {}
            watch.append({"household": h.household_id, "region": reg.get("id"), "profile": p.profil if p else "",
                          "n": len(al), "high": sum(a.severity == "haute" for a in al),
                          "types": dict(Counter(a.anomaly_type for a in al)), "last": max(a.date for a in al).isoformat()})
    watch.sort(key=lambda x: (-x["n"], -x["high"]))
    nhh = Counter(h.region_id for h in Household.objects.all())
    # coupures : lien avec la chaleur (météo du jour de la coupure)
    wx = {(w.region, w.date): w.tmax for w in Weather.objects.all()}
    outs = defaultdict(lambda: {"n": 0, "hours": 0, "hot": 0})
    om = defaultdict(lambda: {"n": 0, "t": []})
    for o in Outage.objects.all():
        reg = region_of(o.region)
        if not reg:
            continue
        t = wx.get((o.region, o.start.date()))
        d = outs[reg["id"]]
        d["n"] += 1
        d["hours"] += o.hours
        d["hot"] += int(t is not None and t >= 35)
        om[o.start.strftime("%Y-%m")]["n"] += 1
    tmonth = defaultdict(list)
    for (rg, d), t in wx.items():
        tmonth[d.strftime("%Y-%m")].append(t)
    months = sorted(set(by_month) | set(om))
    hot_days = sum(1 for t in wx.values() if t >= 35)
    return {
        "regions": [{**{k: r[k] for k in ("id", "fr", "ar")}, "households": nhh.get(r["id"], 0),
                     "types": dict(by_reg.get(r["id"], {})), "total": sum(by_reg.get(r["id"], {}).values()),
                     "per_household": _r(sum(by_reg.get(r["id"], {}).values()) / nhh[r["id"]], 1) if nhh.get(r["id"]) else 0,
                     "outages": outs[r["id"]]["n"], "outage_hours": outs[r["id"]]["hours"], "outages_hot": outs[r["id"]]["hot"]}
                    for r in REGIONS],
        "months": months,
        "by_month": {t: [by_month[m].get(t, 0) for m in months] for t in ("surconsommation", "consommation_nocturne", "ecart_prevision")},
        "outages_month": [om[m]["n"] for m in months],
        "tmax_month": [_r(sum(tmonth[m]) / len(tmonth[m]), 1) if tmonth.get(m) else None for m in months],
        "watch": watch[:15], "total": len(alerts),
        "hot_share": {"hot_days_share": _r(hot_days / max(len(wx), 1) * 100, 1),
                      "outages_on_hot_share": _r(sum(v["hot"] for v in outs.values()) / max(sum(v["n"] for v in outs.values()), 1) * 100, 1)},
        "metrics": (model_quality().get("anomalies") or {}),
    }


# =========================================================================== ADMINISTRATION
def users_payload():
    out = []
    for u in get_user_model().objects.select_related("profile__household").order_by("-date_joined"):
        p = getattr(u, "profile", None)
        out.append({"id": u.id, "email": u.username, "name": u.first_name,
                    "role": p.role if p else ("admin" if u.is_superuser else ""),
                    "household": p.household.household_id if p and p.household else "",
                    "active": u.is_active, "joined": u.date_joined.date().isoformat(),
                    "last_login": u.last_login.isoformat() if u.last_login else None})
    return out


def households_payload():
    linked = set(UserProfile.objects.exclude(household=None).values_list("household__household_id", flat=True))
    return [{"id": h.household_id, "region": (h.region_info or {}).get("fr", h.region), "linked": h.household_id in linked,
             "synthetic": h.is_synthetic} for h in Household.objects.order_by("household_id")]


def _file(p):
    try:
        st = os.stat(p)
        return {"exists": True, "size": st.st_size, "mtime": date.fromtimestamp(st.st_mtime).isoformat()}
    except OSError:
        return {"exists": False}


def datasets_payload():
    def span(qs, f):
        a = qs.aggregate(a=Min(f), b=Max(f))
        return [a["a"].isoformat()[:10] if a["a"] else None, a["b"].isoformat()[:10] if a["b"] else None]
    D, M = settings.ML_DATA_DIR, settings.ML_MODELS_DIR
    f1 = Forecast.objects.filter(kind="backtest", horizon_days=1)
    f7 = Forecast.objects.filter(kind="backtest", horizon_days=7)
    rows = [
        ("weather.csv", D / "raw" / "weather.csv", Weather.objects.count(), span(Weather.objects, "date"), "fetch_weather.py (Open-Meteo)", "observed"),
        ("households.csv", D / "synthetic" / "households.csv", Household.objects.count(), [None, None], "generate_synthetic.py --seed 42", "synthetic"),
        ("readings.csv", D / "synthetic" / "readings.csv", None, [None, None], "generate_synthetic.py --seed 42", "synthetic"),
        ("holidays_used.csv", D / "synthetic" / "holidays_used.csv", Holiday.objects.count(), span(Holiday.objects, "date"), "generate_synthetic.py", "reference"),
        ("outages_used.csv", D / "synthetic" / "outages_used.csv", Outage.objects.count(), span(Outage.objects, "start"), "generate_synthetic.py", "synthetic"),
        ("daily.csv", D / "processed" / "daily.csv", DailyConsumption.objects.filter(source="ml").count(), span(DailyConsumption.objects, "date"), "prepare.py", "synthetic"),
        ("forecast_h1_predictions.csv", D / "processed" / "forecast_h1_predictions.csv", f1.count(), span(f1, "target_date"), "train_forecast.py --horizon 1 --weather-error 2", "synthetic"),
        ("forecast_h7_predictions.csv", D / "processed" / "forecast_h7_predictions.csv", f7.count(), span(f7, "target_date"), "train_forecast.py --horizon 7 --weather-error 2", "synthetic"),
        ("profiles.csv", D / "processed" / "profiles.csv", HouseholdProfile.objects.count(), [None, None], "profiles.py", "synthetic"),
        ("anomalies_flagged.csv", D / "processed" / "anomalies_flagged.csv", Alert.objects.filter(source="ml").count(), span(Alert.objects.filter(source="ml"), "date"), "anomalies.py", "synthetic"),
        ("forecast_h1.joblib", M / "forecast_h1.joblib", None, [None, None], "train_forecast.py --horizon 1 --weather-error 2", "model"),
        ("forecast_h7.joblib", M / "forecast_h7.joblib", None, [None, None], "train_forecast.py --horizon 7 --weather-error 2", "model"),
    ]
    out = [{"name": n, "path": str(p), "rows": c, "span": s, "src": src, "kind": k, "file": _file(p)} for n, p, c, s, src, k in rows]
    user_rows = DailyConsumption.objects.exclude(source="ml")
    out.append({"name": "Relevés des foyers (saisie / import)", "path": "", "rows": user_rows.count(), "span": span(user_rows, "date"),
                "src": "Espace foyer", "kind": "user", "file": {"exists": None}})
    return out


def quality_payload():
    """Qualité mesurée sur les prévisions d'évaluation (prévu contre réel) stockées en base."""
    rows = list(Forecast.objects.filter(kind="backtest", horizon_days=1, actual_kwh__gt=0)
                .values("household_id", "household__region", "target_date", "predicted_kwh", "actual_kwh", "q10", "q90"))
    if not rows:
        return {"n": 0}
    past = {(r["household_id"], r["date"]): r["kwh"] for r in DailyConsumption.objects.values("household_id", "date", "kwh")}

    def agg(rs):
        if not rs:
            return None
        mape = sum(abs(r["actual_kwh"] - r["predicted_kwh"]) / r["actual_kwh"] for r in rs) / len(rs) * 100
        base = [abs(r["actual_kwh"] - past[k]) / r["actual_kwh"] for r in rs
                if (k := (r["household_id"], r["target_date"] - timedelta(days=7))) in past]
        return {"n": len(rs), "mape": round(mape, 2), "base": round(sum(base) / len(base) * 100, 2) if base else None,
                "mae": round(sum(abs(r["actual_kwh"] - r["predicted_kwh"]) for r in rs) / len(rs), 3)}
    tot = agg(rows)
    iv = [r for r in rows if r["q10"] is not None and r["q90"] is not None]
    tot["coverage"] = round(sum(r["q10"] <= r["actual_kwh"] <= r["q90"] for r in iv) / len(iv) * 100, 1) if iv else None
    by_reg = []
    for reg in REGIONS:
        a = agg([r for r in rows if (region_of(r["household__region"]) or {}).get("id") == reg["id"]])
        if a:
            by_reg.append({"id": reg["id"], "fr": reg["fr"], "ar": reg["ar"], **a})
    days = sorted({r["target_date"] for r in rows})
    byd = defaultdict(list)
    for r in rows:
        byd[r["target_date"]].append(r)
    by_day = [{"date": d.isoformat(), "mape": agg(byd[d])["mape"]} for d in days]
    return {**tot, "by_region": by_reg, "by_day": by_day}


def models_payload():
    runs = {}
    for name in ("forecast_h1", "forecast_h7", "profiles", "anomalies"):
        hist = list(ModelRun.objects.filter(name=name).order_by("-imported_at")[:5])
        if hist:
            runs[name] = {"active": hist[0].metrics, "trained_at": timezone.localtime(hist[0].trained_at).isoformat() if hist[0].trained_at else None,
                          "history": [{"trained_at": timezone.localtime(h.trained_at).isoformat() if h.trained_at else None,
                                       "mape": ((h.metrics.get("test") or {}).get("ensemble") or {}).get("MAPE_%")} for h in hist]}
    fut = Forecast.objects.filter(kind="future")
    last = fut.aggregate(m=Max("generated_at"))["m"]
    clusters = list(HouseholdProfile.objects.values("cluster", "profil").annotate(n=Count("id")).order_by("cluster"))
    return {"runs": runs, "quality": quality_payload(),
            "inference": {"count": fut.count(), "households": fut.values("household").distinct().count(),
                          "last": last.isoformat() if last else None,
                          "files": {h: _file(settings.ML_MODELS_DIR / f"forecast_h{h}.joblib") for h in (1, 7)}},
            "clusters": clusters}


def pipeline_payload():
    from .pipeline import STEPS
    return {"steps": [{"id": k, "label": v[0], "script": v[1]} for k, v in STEPS.items()],
            "runs": [{"id": r.id, "status": r.status, "steps": r.steps, "log": r.log[-6000:],
                      "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                      "by": r.started_by.username if r.started_by else ""} for r in PipelineRun.objects.all()[:5]],
            "scripts_dir": str(settings.ML_SCRIPTS_DIR)}


def tariff_payload():
    billing.ensure_default_bands()
    return {"bands": [{"id": b.id, "label": b.label, "max": b.max_kwh_year, "price": float(b.price_dt)} for b in TariffBand.objects.all()],
            "source": billing.SOURCE}


def admin_overview():
    U = get_user_model()
    roles = Counter(UserProfile.objects.values_list("role", flat=True))
    return {"users": U.objects.count(), "active": U.objects.filter(is_active=True).count(), "roles": dict(roles),
            "households": Household.objects.count(), "linked": UserProfile.objects.exclude(household=None).count(),
            "daily": DailyConsumption.objects.count(), "alerts_open": Alert.objects.filter(is_resolved=False).count(),
            "future": Forecast.objects.filter(kind="future").count(),
            "models_ok": all((settings.ML_MODELS_DIR / f"forecast_h{h}.joblib").exists() for h in (1, 7)),
            "llm": bool(settings.ANTHROPIC_API_KEY)}
