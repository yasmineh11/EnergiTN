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


# ==========================================================
# OUTILS COMMUNS
# ==========================================================

def as_float(value, default=None):
    """Convertit une valeur numérique Django en float exploitable en JS."""
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def role_of(user):
    """Retourne le rôle associé à l'utilisateur connecté."""
    if not user.is_authenticated:
        return None

    profile = getattr(user, "profile", None)

    if profile:
        return profile.role

    return "admin" if user.is_superuser else None


# ==========================================================
# 1. DONNEES DU FOYER
# ==========================================================

def foyer_payload(h):
    """Construit les données du tableau de bord d'un foyer."""

    forecasts = list(
        Forecast.objects.filter(
            household=h,
            horizon=1,
        ).order_by("-date")[:7]
    )[::-1]

    history_qs = DailyConsumption.objects.filter(
        household=h
    )

    if forecasts:
        history_qs = history_qs.filter(
            date__lt=forecasts[0].date
        )

    history = list(
        history_qs.order_by("-date")[:90]
    )[::-1]

    if not history or not forecasts:
        return None

    flagged_dates = set(
        Alert.objects.filter(
            household=h
        ).values_list("date", flat=True)
    )

    profile = getattr(h, "profile", None)

    region_name_raw = (
        h.region.name if h.region else ""
    )

    region = (
        region_of(region_name_raw)
        if region_name_raw else None
    )

    region_name = (
        region["fr"]
        if region
        else (region_name_raw or "Région inconnue")
    )

    who = f"{h.code} · {region_name}"

    if profile:
        who += f" · {profile.label}"

    return {
        "who": who,

        "days": [
            {
                "date": day.date.isoformat(),
                "kwh": as_float(day.kwh, 0),
                "tmax": as_float(day.tmax),
                "anomaly": day.date in flagged_dates,
            }
            for day in history
        ],

        "forecast": [
            {
                "date": forecast.date.isoformat(),
                "pred": as_float(forecast.predicted),
                "q10": as_float(forecast.low),
                "q90": as_float(forecast.high),
            }
            for forecast in forecasts
        ],

        "profile": {
            "name": profile.label if profile else "",
            "cluster": profile.cluster if profile else None,
            "evening": None,
            "night": None,
            "summer": None,
        },
    }


# ==========================================================
# 2. DONNEES DE L'ANALYSTE
# ==========================================================

def operator_payload():
    """
    Construit les données globales de l'analyste.

    Format retourné :
    {
        dates: [...],
        regions: [
            {
                id, fr, ar, cap, s, x, y,
                util: [...],
                tmax: [...]
            }
        ],
        anomalies: [
            [region_id, nombre, type_dominant]
        ]
    }
    """

    # ------------------------------------------------------
    # Dates des prévisions J+1
    # ------------------------------------------------------

    dates = list(
        Forecast.objects.filter(horizon=1)
        .values_list("date", flat=True)
        .distinct()
        .order_by("-date")[:7]
    )

    dates.sort()

    if not dates:
        return {
            "dates": [],
            "regions": [],
            "anomalies": [],
        }

    # ------------------------------------------------------
    # Regrouper les foyers par région
    # ------------------------------------------------------

    households_by_region = {}

    households = Household.objects.select_related(
        "region"
    ).all()

    for household in households:

        if not household.region:
            continue

        region = region_of(household.region.name)

        if region:
            households_by_region.setdefault(
                region["id"], []
            ).append(household.id)

    # ------------------------------------------------------
    # Calcul des indicateurs de chaque région
    # ------------------------------------------------------

    regions_data = []

    for region in REGIONS:

        household_ids = households_by_region.get(
            region["id"], []
        )

        history = DailyConsumption.objects.filter(
            household_id__in=household_ids
        )

        # Moyenne journalière historique maximale.
        top = (
            history
            .filter(kwh__isnull=False)
            .values("date")
            .annotate(m=Avg("kwh"))
            .order_by("-m")
            .first()
        )

        top_mean = as_float(
            top.get("m") if top else None
        )

        # Référence utilisée pour normaliser la charge.
        reference = (
            top_mean * 1.25
            if top_mean is not None and top_mean > 0
            else None
        )

        # Moyennes des prévisions par date.
        forecast_rows = (
            Forecast.objects.filter(
                household_id__in=household_ids,
                horizon=1,
                date__in=dates,
                predicted__isnull=False,
            )
            .values("date")
            .annotate(m=Avg("predicted"))
        )

        forecast_means = {
            row["date"]: as_float(row["m"])
            for row in forecast_rows
        }

        # Température moyenne par date.
        temperature_rows = (
            history
            .filter(
                date__in=dates,
                tmax__isnull=False,
            )
            .values("date")
            .annotate(t=Avg("tmax"))
        )

        temperature_means = {
            row["date"]: as_float(row["t"])
            for row in temperature_rows
        }

        # Taux de charge journalier.
        utilization = []

        for day in dates:

            forecast_mean = forecast_means.get(day)

            if (
                reference is not None
                and reference > 0
                and forecast_mean is not None
            ):
                utilization.append(
                    round(forecast_mean / reference, 4)
                )
            else:
                # None signifie que les données sont absentes.
                utilization.append(None)

        regions_data.append({
            "id": region["id"],
            "fr": region["fr"],
            "ar": region["ar"],
            "cap": as_float(region["cap"], 0),
            "s": as_float(region["s"], 0),
            "x": as_float(region["x"], 0),
            "y": as_float(region["y"], 0),

            "util": utilization,

            "tmax": [
                temperature_means.get(day)
                for day in dates
            ],
        })

    # ------------------------------------------------------
    # Anomalies des 30 derniers jours disponibles
    # ------------------------------------------------------

    anomalies = []

    last_alert_date = (
        Alert.objects.order_by("-date")
        .values_list("date", flat=True)
        .first()
    )

    count_by_region = {}
    types_by_region = {}

    if last_alert_date:

        alerts = (
            Alert.objects.filter(
                date__gte=last_alert_date - timedelta(days=30),
                date__lte=last_alert_date,
            )
            .select_related("household__region")
        )

        for alert in alerts:

            if not alert.household.region:
                continue

            region = region_of(
                alert.household.region.name
            )

            if not region:
                continue

            region_id = region["id"]

            count_by_region[region_id] = (
                count_by_region.get(region_id, 0) + 1
            )

            alert_type = alert.kind or "Autre"

            types_by_region.setdefault(
                region_id, {}
            )

            types_by_region[region_id][alert_type] = (
                types_by_region[region_id].get(
                    alert_type, 0
                ) + 1
            )

    for region in REGIONS:

        type_counts = types_by_region.get(
            region["id"], {}
        )

        dominant_type = (
            max(type_counts, key=type_counts.get)
            if type_counts
            else "–"
        )

        anomalies.append([
            region["id"],
            count_by_region.get(region["id"], 0),
            dominant_type,
        ])

    anomalies.sort(
        key=lambda item: -item[1]
    )

    return {
        "dates": [
            day.isoformat()
            for day in dates
        ],
        "regions": regions_data,
        "anomalies": anomalies,
    }


# ==========================================================
# 3. GESTION DES UTILISATEURS
# ==========================================================

def users_payload():
    """Construit la liste des utilisateurs pour l'administration."""

    output = []

    users = (
        get_user_model().objects
        .select_related("profile__household")
        .order_by("username")
    )

    for user in users:

        profile = getattr(user, "profile", None)

        output.append({
            "id": user.id,
            "email": user.email or user.username,
            "name": user.first_name,

            "role": (
                profile.role
                if profile
                else (
                    "admin"
                    if user.is_superuser
                    else ""
                )
            ),

            "household": (
                profile.household.code
                if profile and profile.household
                else ""
            ),

            "active": user.is_active,
        })

    return output


# ==========================================================
# 4. QUALITE DES PREVISIONS
# ==========================================================

def quality_payload():
    """Calcule les indicateurs de qualité des prévisions J+1."""

    rows = list(
        Forecast.objects.filter(
            horizon=1,
            actual__isnull=False,
            actual__gt=0,
            predicted__isnull=False,
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
        return {
            "n": 0,
            "mape": None,
            "base": None,
            "mae": None,
            "coverage": None,
            "by_region": [],
            "by_day": [],
        }

    past = {
        (row["household_id"], row["date"]): as_float(row["kwh"])
        for row in DailyConsumption.objects.filter(
            kwh__isnull=False
        ).values(
            "household_id",
            "date",
            "kwh",
        )
    }

    def aggregate_metrics(records):

        valid = [
            row for row in records
            if (
                row["actual"] is not None
                and row["actual"] > 0
                and row["predicted"] is not None
            )
        ]

        if not valid:
            return None

        mape = (
            sum(
                abs(
                    float(row["actual"])
                    - float(row["predicted"])
                ) / float(row["actual"])
                for row in valid
            )
            / len(valid)
            * 100
        )

        baseline_errors = []

        for row in valid:

            previous_key = (
                row["household_id"],
                row["date"] - timedelta(days=7),
            )

            previous_value = past.get(previous_key)

            if previous_value is not None:

                baseline_errors.append(
                    abs(
                        float(row["actual"])
                        - previous_value
                    ) / float(row["actual"])
                )

        mae = (
            sum(
                abs(
                    float(row["actual"])
                    - float(row["predicted"])
                )
                for row in valid
            )
            / len(valid)
        )

        return {
            "n": len(valid),
            "mape": round(mape, 2),

            "base": (
                round(
                    sum(baseline_errors)
                    / len(baseline_errors)
                    * 100,
                    2,
                )
                if baseline_errors
                else None
            ),

            "mae": round(mae, 3),
        }

    total = aggregate_metrics(rows)

    if total is None:
        return {
            "n": 0,
            "mape": None,
            "base": None,
            "mae": None,
            "coverage": None,
            "by_region": [],
            "by_day": [],
        }

    # Couverture des intervalles de prévision.
    interval_rows = [
        row for row in rows
        if (
            row["low"] is not None
            and row["high"] is not None
        )
    ]

    total["coverage"] = (
        round(
            sum(
                float(row["low"])
                <= float(row["actual"])
                <= float(row["high"])
                for row in interval_rows
            )
            / len(interval_rows)
            * 100,
            1,
        )
        if interval_rows
        else None
    )

    # Qualité par région.
    by_region = []

    for region in REGIONS:

        region_metrics = aggregate_metrics([
            row for row in rows
            if (
                region_of(
                    row["household__region__name"] or ""
                ) or {}
            ).get("id") == region["id"]
        ])

        if region_metrics:

            by_region.append({
                "id": region["id"],
                "fr": region["fr"],
                "ar": region["ar"],
                **region_metrics,
            })

    # Qualité par jour.
    days = sorted({
        row["date"]
        for row in rows
    })[-30:]

    by_day = []

    for day in days:

        day_metrics = aggregate_metrics([
            row for row in rows
            if row["date"] == day
        ])

        by_day.append({
            "date": day.isoformat(),
            "mape": (
                day_metrics["mape"]
                if day_metrics
                else None
            ),
        })

    return {
        **total,
        "by_region": by_region,
        "by_day": by_day,
    }


# ==========================================================
# 5. DATASETS
# ==========================================================

def datasets_payload():
    """Construit les informations sur les jeux de données importés."""

    def date_span(queryset, field):

        values = queryset.aggregate(
            a=Min(field),
            b=Max(field),
        )

        return [
            values["a"].isoformat()
            if values["a"] else None,

            values["b"].isoformat()
            if values["b"] else None,
        ]

    forecast_j1 = Forecast.objects.filter(
        horizon=1
    )

    forecast_j7 = Forecast.objects.filter(
        horizon=7
    )

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
            "span": date_span(
                DailyConsumption.objects,
                "date",
            ),
            "src": "prepare.py",
        },
        {
            "name": "forecast_h1_predictions.csv",
            "rows": forecast_j1.count(),
            "span": date_span(
                forecast_j1,
                "date",
            ),
            "src": "train_forecast.py --horizon 1",
        },
        {
            "name": "forecast_h7_predictions.csv",
            "rows": forecast_j7.count(),
            "span": date_span(
                forecast_j7,
                "date",
            ),
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
            "span": date_span(
                Alert.objects,
                "date",
            ),
            "src": "anomalies.py",
        },
    ]


# ==========================================================
# 6. ADMINISTRATION
# ==========================================================

def admin_payload():
    """Construit les données affichées dans l'espace administrateur."""

    return {
        "users": users_payload(),

        "households": list(
            Household.objects.order_by("code").values_list(
                "code",
                flat=True,
            )
        ),

        "datasets": datasets_payload(),

        "quality": quality_payload(),
    }