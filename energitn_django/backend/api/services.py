"""Construit les données JSON utilisées par les interfaces et exposées par l'API."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Min, Max

from energy.models import (
    Household,
    DailyConsumption,
    Forecast,
    Alert,
    Profile,
)

from .regions import REGIONS, region_of


def role_of(user):
    if not user.is_authenticated:
        return None

    p = getattr(user, "profile", None)

    if p:
        return p.role

    return "admin" if user.is_superuser else None


# ==========================================================
# 1. DONNEES DU FOYER
# ==========================================================

def foyer_payload(h):

    # Prévisions J+1
    fc = list(
        Forecast.objects.filter(
            household=h,
            horizon=1
        ).order_by("-date")[:7]
    )[::-1]

    # Consommations historiques
    qs = DailyConsumption.objects.filter(household=h)

    if fc:
        qs = qs.filter(date__lt=fc[0].date)

    hist = list(qs.order_by("-date")[:90])[::-1]

    if not hist or not fc:
        return None

    # Dates avec alertes
    flagged = set(
        Alert.objects.filter(
            household=h
        ).values_list("date", flat=True)
    )

    # Profil énergétique
    p = getattr(h, "profile", None)

    # Région
    reg = region_of(h.region.name)

    region_name = reg["fr"] if reg else h.region.name

    who = f"{h.code} · {region_name}"

    if p:
        who += f" · {p.label}"

    return {
        "who": who,

        "days": [
            {
                "date": d.date.isoformat(),
                "kwh": d.kwh,
                "tmax": d.tmax,
                "anomaly": d.date in flagged,
            }
            for d in hist
        ],

        "forecast": [
            {
                "date": f.date.isoformat(),
                "pred": f.predicted,
                "q10": f.low,
                "q90": f.high,
            }
            for f in fc
        ],

        "profile": {
            "name": p.label if p else "",
            "cluster": p.cluster if p else None,
            "evening": None,
            "night": None,
            "summer": None,
        },
    }


# ==========================================================
# 2. DONNEES DE L'ANALYSTE
# ==========================================================

def operator_payload():

    dates = sorted(
        Forecast.objects.filter(
            horizon=1
        ).values_list(
            "date", flat=True
        ).distinct().order_by("-date")[:7]
    )

    if not dates:
        return None

    by_reg = {}

    for h in Household.objects.select_related("region").all():

        reg = region_of(h.region.name)

        if reg:
            by_reg.setdefault(reg["id"], []).append(h.id)

    regions = []

    for reg in REGIONS:

        ids = by_reg.get(reg["id"], [])

        hist = DailyConsumption.objects.filter(
            household_id__in=ids
        )

        top = (
            hist.values("date")
            .annotate(m=Avg("kwh"))
            .order_by("-m")
            .first()
        )

        ref = top["m"] * 1.25 if top else None

        fm = {
            r["date"]: r["m"]
            for r in (
                Forecast.objects.filter(
                    household_id__in=ids,
                    horizon=1,
                    date__in=dates,
                )
                .values("date")
                .annotate(m=Avg("predicted"))
            )
        }

        tm = {
            r["date"]: r["t"]
            for r in (
                hist.filter(date__in=dates)
                .values("date")
                .annotate(t=Avg("tmax"))
            )
        }

        regions.append({
            **{
                k: reg[k]
                for k in ("id", "fr", "ar", "cap", "x", "y", "s")
            },

            "util": [
                round(fm[d] / ref, 4)
                if ref and d in fm else 0
                for d in dates
            ],

            "tmax": [
                tm.get(d)
                for d in dates
            ],
        })

    # Analyse des alertes
    anomalies = []

    last = Alert.objects.order_by(
        "-date"
    ).values_list("date", flat=True).first()

    cnt, typ = {}, {}

    if last:

        alerts = Alert.objects.filter(
            date__gte=last - timedelta(days=30)
        ).select_related("household__region")

        for a in alerts:

            reg = region_of(a.household.region.name)

            if reg:
                rid = reg["id"]

                cnt[rid] = cnt.get(rid, 0) + 1

                typ.setdefault(rid, {}).setdefault(a.kind, 0)

                typ[rid][a.kind] += 1

    for reg in REGIONS:

        t = typ.get(reg["id"])

        anomalies.append([
            reg["id"],
            cnt.get(reg["id"], 0),
            max(t, key=t.get) if t else "–",
        ])

    anomalies.sort(key=lambda a: -a[1])

    return {
        "dates": [d.isoformat() for d in dates],
        "regions": regions,
        "anomalies": anomalies,
    }


# ==========================================================
# 3. GESTION DES UTILISATEURS
# ==========================================================

def users_payload():

    out = []

    users = get_user_model().objects.select_related(
        "profile__household"
    ).order_by("username")

    for u in users:

        p = getattr(u, "profile", None)

        out.append({
            "id": u.id,
            "email": u.email or u.username,
            "name": u.first_name,

            "role": (
                p.role if p
                else ("admin" if u.is_superuser else "")
            ),

            "household": (
                p.household.code
                if p and p.household else ""
            ),

            "active": u.is_active,
        })

    return out


# ==========================================================
# 4. QUALITE DES PREVISIONS
# ==========================================================

def quality_payload():

    rows = list(
        Forecast.objects.filter(
            horizon=1,
            actual__isnull=False
        ).values(
            "household_id",
            "household__region__name",
            "date",
            "predicted",
            "actual",
            "low",
            "high",
        )
    )

    if not rows:
        return {"n": 0}

    past = {
        (r["household_id"], r["date"]): r["kwh"]
        for r in DailyConsumption.objects.values(
            "household_id", "date", "kwh"
        )
    }

    def agg(rs):

        ok = [
            r for r in rs
            if r["actual"] is not None and r["actual"] > 0
        ]

        if not ok:
            return None

        mape = (
            sum(
                abs(r["actual"] - r["predicted"]) / r["actual"]
                for r in ok
            ) / len(ok) * 100
        )

        base = [
            abs(
                r["actual"] -
                past[(
                    r["household_id"],
                    r["date"] - timedelta(days=7)
                )]
            ) / r["actual"]

            for r in ok

            if (
                r["household_id"],
                r["date"] - timedelta(days=7)
            ) in past
        ]

        return {
            "n": len(ok),
            "mape": round(mape, 2),

            "base": (
                round(sum(base) / len(base) * 100, 2)
                if base else None
            ),

            "mae": round(
                sum(
                    abs(r["actual"] - r["predicted"])
                    for r in ok
                ) / len(ok),
                3
            ),
        }

    tot = agg(rows)

    iv = [
        r for r in rows
        if r["low"] is not None and r["high"] is not None
    ]

    tot["coverage"] = (
        round(
            sum(
                r["low"] <= r["actual"] <= r["high"]
                for r in iv
            ) / len(iv) * 100,
            1
        )
        if iv else None
    )

    by_reg = []

    for reg in REGIONS:

        a = agg([
            r for r in rows
            if (
                region_of(r["household__region__name"]) or {}
            ).get("id") == reg["id"]
        ])

        if a:
            by_reg.append({
                "id": reg["id"],
                "fr": reg["fr"],
                "ar": reg["ar"],
                **a,
            })

    days = sorted({
        r["date"] for r in rows
    })[-30:]

    by_day = [
        {
            "date": d.isoformat(),
            "mape": (
                agg([
                    r for r in rows
                    if r["date"] == d
                ]) or {}
            ).get("mape"),
        }
        for d in days
    ]

    return {
        **tot,
        "by_region": by_reg,
        "by_day": by_day,
    }


# ==========================================================
# 5. DATASETS
# ==========================================================

def datasets_payload():

    def span(qs, field):

        a = qs.aggregate(
            a=Min(field),
            b=Max(field)
        )

        return [
            a["a"].isoformat() if a["a"] else None,
            a["b"].isoformat() if a["b"] else None,
        ]

    f1 = Forecast.objects.filter(horizon=1)
    f7 = Forecast.objects.filter(horizon=7)

    return [
        {
            "name": "households.csv",
            "rows": Household.objects.count(),
            "span": [None, None],
            "src": "generate_synthetic.py (seed 42)",
        },

        {
            "name": "daily.csv",
            "rows": DailyConsumption.objects.count(),
            "span": span(DailyConsumption.objects, "date"),
            "src": "prepare.py",
        },

        {
            "name": "forecast_h1_predictions.csv",
            "rows": f1.count(),
            "span": span(f1, "date"),
            "src": "train_forecast.py --horizon 1",
        },

        {
            "name": "forecast_h7_predictions.csv",
            "rows": f7.count(),
            "span": span(f7, "date"),
            "src": "train_forecast.py --horizon 7",
        },

        {
            "name": "profiles.csv",
            "rows": Profile.objects.count(),
            "span": [None, None],
            "src": "profiles.py",
        },

        {
            "name": "anomalies_flagged.csv",
            "rows": Alert.objects.count(),
            "span": span(Alert.objects, "date"),
            "src": "anomalies.py",
        },
    ]


# ==========================================================
# 6. ADMINISTRATION
# ==========================================================

def admin_payload():

    return {
        "users": users_payload(),

        "households": list(
            Household.objects.order_by("code").values_list(
                "code", flat=True
            )
        ),

        "datasets": datasets_payload(),

        "quality": quality_payload(),
    }