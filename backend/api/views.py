"""API REST (Django REST Framework). Mêmes règles d'accès que les pages : un foyer ne voit que ses données."""
from datetime import date

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import insights, ml
from .facts import household_facts
from .models import Alert, Forecast, Household, HouseholdProfile
from .serializers import (AlertSerializer, ForecastSerializer, HouseholdProfileSerializer, HouseholdSerializer,
                          ReadingSerializer)
from .services import analyst_anomalies, analyst_forecast, analyst_profiles, foyer_dashboard, models_payload, role_of


class Scoped:
    """Un foyer ne voit que ses propres données ; analyste et admin voient tout."""
    lookup = "household"

    def get_queryset(self):
        qs = super().get_queryset()
        role = role_of(self.request.user)
        if role == "foyer":
            hh = self.request.user.profile.household
            return qs.filter(**{self.lookup: hh.pk if hh else None})
        return qs if role in ("analyste", "admin") else qs.none()


class HouseholdViewSet(Scoped, viewsets.ReadOnlyModelViewSet):
    queryset = Household.objects.all().order_by("household_id")
    serializer_class = HouseholdSerializer
    lookup = "pk"


class ForecastViewSet(Scoped, viewsets.ReadOnlyModelViewSet):
    queryset = Forecast.objects.select_related("household").order_by("household__household_id", "target_date")
    serializer_class = ForecastSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("kind") in ("future", "backtest"):
            qs = qs.filter(kind=p["kind"])
        if p.get("horizon", "").isdigit():
            qs = qs.filter(horizon_days=int(p["horizon"]))
        if p.get("household_id"):
            qs = qs.filter(household__household_id=p["household_id"])
        return qs


class ProfileViewSet(Scoped, viewsets.ReadOnlyModelViewSet):
    queryset = HouseholdProfile.objects.select_related("household").order_by("household__household_id")
    serializer_class = HouseholdProfileSerializer


class AlertViewSet(Scoped, viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.select_related("household")
    serializer_class = AlertSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        sev = self.request.query_params.get("severity")
        return qs.filter(severity__iexact=sev) if sev else qs


@api_view(["GET"])
def accueil_api(request):
    return Response({"message": "API ÉnergiTN", "role": role_of(request.user), "endpoints": {
        "households": "/api/households/", "forecasts": "/api/forecasts/?kind=future", "profiles": "/api/profiles/",
        "anomalies": "/api/anomalies/", "foyer_dashboard": "/api/foyer/dashboard/", "foyer_facts": "/api/foyer/facts/",
        "foyer_readings (POST)": "/api/foyer/readings/", "analyste": "/api/operator/overview/",
        "analyste_profils": "/api/operator/profiles/", "analyste_anomalies": "/api/operator/anomalies/", "modeles": "/api/models/",
        "ml_health": "/api/ml/health/", "ml_predict (POST)": "/api/ml/predict/", "foyer_scenario": "/api/foyer/scenario/?delta=4"}})


def _household(request):
    if role_of(request.user) == "foyer":
        return request.user.profile.household
    if role_of(request.user) in ("analyste", "admin"):
        return Household.objects.filter(household_id=request.query_params.get("household_id")).first()
    return None


@api_view(["GET"])
def foyer_dashboard_api(request):
    h = _household(request)
    data = foyer_dashboard(h) if h else None
    return Response(data) if data else Response({"detail": "Aucune donnée pour ce foyer."}, status=404)


@api_view(["GET"])
def foyer_facts_api(request):
    """Le JSON de faits utilisé par l'assistant IA (guide, rôle C)."""
    h = _household(request)
    return Response(household_facts(h)) if h else Response({"detail": "Foyer introuvable."}, status=404)


@api_view(["POST"])
def foyer_readings_api(request):
    if role_of(request.user) != "foyer" or not request.user.profile.household:
        return Response({"detail": "Réservé aux comptes foyer liés à un foyer."}, status=403)
    s = ReadingSerializer(data=request.data, many=isinstance(request.data, list))
    s.is_valid(raise_exception=True)
    items = [(r["date"], r["kwh"]) for r in (s.validated_data if isinstance(s.validated_data, list) else [s.validated_data])]
    if any(d > timezone.localdate() for d, _ in items):
        return Response({"detail": "Date future refusée."}, status=400)
    res = ml.save_readings(request.user.profile.household, items, source="import")
    return Response({"saved": res["saved"], "forecasts": res["forecasts"], "alerts": AlertSerializer(res["alerts"], many=True).data},
                    status=status.HTTP_201_CREATED)


def _analyst(fn):
    @api_view(["GET"])
    def view(request):
        if role_of(request.user) not in ("analyste", "admin"):
            return Response({"detail": "Réservé aux analystes et administrateurs."}, status=403)
        data = fn()
        return Response(data) if data else Response({"detail": "Aucune prévision calculée."}, status=404)
    return view


operator_overview = _analyst(analyst_forecast)
operator_profiles = _analyst(analyst_profiles)
operator_anomalies = _analyst(analyst_anomalies)
models_api = _analyst(models_payload)


# --------------------------------------------------------------------------- liaison ML à la demande (guide, option B)
@api_view(["GET"])
def ml_health_api(request):
    """État de la liaison Django <-> ML : fichiers .joblib, versions, fraîcheur de l'inférence."""
    if role_of(request.user) not in ("analyste", "admin"):
        return Response({"detail": "Réservé aux analystes et administrateurs."}, status=403)
    return Response({**insights.ml_health(), "drift": insights.drift_report()})


@api_view(["POST"])
def ml_predict_api(request):
    """Recalcule à la demande les prévisions J+1…J+7 d'un foyer avec les modèles .joblib.
    Foyer : son propre foyer uniquement. Analyste/admin : {"household_id": "H004"}."""
    role = role_of(request.user)
    if role == "foyer":
        h = request.user.profile.household
    elif role in ("analyste", "admin"):
        h = Household.objects.filter(household_id=request.data.get("household_id")).first()
    else:
        return Response({"detail": "Accès refusé."}, status=403)
    if not h:
        return Response({"detail": "Foyer introuvable."}, status=404)
    try:
        n = ml.forecast_household(h)
    except ml.ModelUnavailable as e:
        return Response({"detail": str(e)}, status=503)
    if not n:
        return Response({"detail": "Historique insuffisant (14 jours minimum).", "forecasts": []}, status=422)
    qs = Forecast.objects.filter(household=h, kind="future").order_by("target_date")
    return Response({"household_id": h.household_id, "forecasts": ForecastSerializer(qs, many=True).data})


@api_view(["GET"])
def foyer_scenario_api(request):
    """Jumeau numérique : les modèles recalculent la semaine avec +x °C (0 à 8)."""
    h = _household(request)
    if not h:
        return Response({"detail": "Foyer introuvable."}, status=404)
    try:
        delta = max(0.0, min(8.0, float(request.query_params.get("delta", 4))))
    except ValueError:
        return Response({"detail": "Paramètre delta invalide."}, status=400)
    try:
        data = insights.forecast_scenario(h, delta)
    except ml.ModelUnavailable as e:
        return Response({"detail": str(e)}, status=503)
    return Response(data) if data else Response({"detail": "Historique insuffisant."}, status=422)
