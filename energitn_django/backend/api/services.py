"""Construit les données JSON utilisées par les deux interfaces (et exposées par l'API)."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Avg, Min, Max
from .models import Household, DailyConsumption, Forecast, Alert, HouseholdProfile
from .regions import REGIONS, region_of


def role_of(user):
    if not user.is_authenticated:
        return None
    p = getattr(user, "profile", None)
    if p:
        return p.role
    return "admin" if user.is_superuser else None


def foyer_payload(h):
    fc = list(Forecast.objects.filter(household=h, horizon_days=1).order_by("-target_date")[:7])[::-1]
    qs = DailyConsumption.objects.filter(household=h)
    if fc:
        qs = qs.filter(date__lt=fc[0].target_date)
    hist = list(qs.order_by("-date")[:90])[::-1]
    if not hist or not fc:
        return None
    flagged = set(Alert.objects.filter(household=h).values_list("date", flat=True))
    p = getattr(h, "profile", None)
    reg = region_of(h.region)
    who = f"{h.household_id} · {reg['fr'] if reg else h.region}" + (f" · {p.profil}" if p else "")
    return {
        "who": who,
        "days": [{"date": d.date.isoformat(), "kwh": d.kwh, "tmax": d.tmax,
                  "anomaly": d.date in flagged} for d in hist],
        "forecast": [{"date": f.target_date.isoformat(), "pred": f.predicted_kwh,
                      "q10": f.q10, "q90": f.q90} for f in fc],
        "profile": {"name": p.profil if p else "",
                    "evening": p.evening_share if p else None,
                    "night": p.night_share if p else None,
                    "summer": p.summer_ratio if p else None},
    }


def operator_payload():
    dates = sorted(Forecast.objects.filter(horizon_days=1).values_list("target_date", flat=True)
                   .distinct().order_by("-target_date")[:7])
    if not dates:
        return None
    by_reg = {}
    for h in Household.objects.all():
        if h.region_id:
            by_reg.setdefault(h.region_id, []).append(h.id)
    regions = []
    for reg in REGIONS:
        ids = by_reg.get(reg["id"], [])
        hist = DailyConsumption.objects.filter(household_id__in=ids)
        top = hist.values("date").annotate(m=Avg("kwh")).order_by("-m").first()
        ref = top["m"] * 1.25 if top else None   # référence : record historique moyen par foyer + 25 %
        fm = {r["target_date"]: r["m"] for r in Forecast.objects.filter(
            household_id__in=ids, horizon_days=1, target_date__in=dates
        ).values("target_date").annotate(m=Avg("predicted_kwh"))}
        tm = {r["date"]: r["t"] for r in hist.filter(date__in=dates).values("date").annotate(t=Avg("tmax"))}
        regions.append({
            **{k: reg[k] for k in ("id", "fr", "ar", "cap", "x", "y", "s")},
            "util": [round(fm[d] / ref, 4) if ref and d in fm else 0 for d in dates],
            "tmax": [tm.get(d) for d in dates],
        })
    anomalies = []
    last = Alert.objects.order_by("-date").values_list("date", flat=True).first()
    cnt, typ = {}, {}
    if last:
        for a in Alert.objects.filter(date__gte=last - timedelta(days=30), household__isnull=False).select_related("household"):
            rid = a.household.region_id
            if rid:
                cnt[rid] = cnt.get(rid, 0) + 1
                typ.setdefault(rid, {}).setdefault(a.anomaly_type, 0)
                typ[rid][a.anomaly_type] += 1
    for reg in REGIONS:
        t = typ.get(reg["id"])
        anomalies.append([reg["id"], cnt.get(reg["id"], 0), max(t, key=t.get) if t else "–"])
    anomalies.sort(key=lambda a: -a[1])
    return {"dates": [d.isoformat() for d in dates], "regions": regions, "anomalies": anomalies}


def users_payload():
    out = []
    for u in get_user_model().objects.select_related("profile__household").order_by("username"):
        p = getattr(u, "profile", None)
        out.append({"id": u.id, "email": u.username, "name": u.first_name,
                    "role": p.role if p else ("admin" if u.is_superuser else ""),
                    "household": p.household.household_id if p and p.household else "",
                    "active": u.is_active})
    return out


def quality_payload():
    """Fiabilité des prévisions J+1 : erreur du modèle, comparée à la baseline « même jour la semaine dernière »."""
    rows = list(Forecast.objects.filter(horizon_days=1, actual_kwh__isnull=False)
                .values("household_id", "household__region", "target_date", "predicted_kwh", "actual_kwh", "q10", "q90"))
    if not rows:
        return {"n": 0}
    past = {(r["household_id"], r["date"]): r["kwh"] for r in DailyConsumption.objects.values("household_id", "date", "kwh")}
    def agg(rs):
        ok = [r for r in rs if r["actual_kwh"] > 0]
        if not ok:
            return None
        mape = sum(abs(r["actual_kwh"] - r["predicted_kwh"]) / r["actual_kwh"] for r in ok) / len(ok) * 100
        base = [abs(r["actual_kwh"] - past[(r["household_id"], r["target_date"] - timedelta(days=7))]) / r["actual_kwh"]
                for r in ok if (r["household_id"], r["target_date"] - timedelta(days=7)) in past]
        return {"n": len(ok), "mape": round(mape, 2), "base": round(sum(base) / len(base) * 100, 2) if base else None,
                "mae": round(sum(abs(r["actual_kwh"] - r["predicted_kwh"]) for r in ok) / len(ok), 3)}
    tot = agg(rows)
    iv = [r for r in rows if r["q10"] is not None and r["q90"] is not None]
    tot["coverage"] = round(sum(r["q10"] <= r["actual_kwh"] <= r["q90"] for r in iv) / len(iv) * 100, 1) if iv else None
    by_reg = []
    for reg in REGIONS:
        a = agg([r for r in rows if (region_of(r["household__region"]) or {}).get("id") == reg["id"]])
        if a:
            by_reg.append({"id": reg["id"], "fr": reg["fr"], "ar": reg["ar"], **a})
    days = sorted({r["target_date"] for r in rows})[-30:]
    by_day = [{"date": d.isoformat(), "mape": (agg([r for r in rows if r["target_date"] == d]) or {}).get("mape")} for d in days]
    return {**tot, "by_region": by_reg, "by_day": by_day}


def datasets_payload():
    def span(qs, f):
        a = qs.aggregate(a=Min(f), b=Max(f))
        return [a["a"].isoformat() if a["a"] else None, a["b"].isoformat() if a["b"] else None]
    f1, f7 = Forecast.objects.filter(horizon_days=1), Forecast.objects.filter(horizon_days=7)
    return [
        {"name": "households.csv", "rows": Household.objects.count(), "span": [None, None], "src": "generate_synthetic.py (seed 42)"},
        {"name": "daily.csv", "rows": DailyConsumption.objects.count(), "span": span(DailyConsumption.objects, "date"), "src": "prepare.py"},
        {"name": "forecast_h1_predictions.csv", "rows": f1.count(), "span": span(f1, "target_date"), "src": "train_forecast.py --horizon 1"},
        {"name": "forecast_h7_predictions.csv", "rows": f7.count(), "span": span(f7, "target_date"), "src": "train_forecast.py --horizon 7"},
        {"name": "profiles.csv", "rows": HouseholdProfile.objects.count(), "span": [None, None], "src": "profiles.py"},
        {"name": "anomalies_flagged.csv", "rows": Alert.objects.count(), "span": span(Alert.objects, "date"), "src": "anomalies.py"},
    ]


def admin_payload():
    return {"users": users_payload(), "households": list(Household.objects.order_by("household_id").values_list("household_id", flat=True)),
            "datasets": datasets_payload(), "quality": quality_payload()}
