from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Household, Forecast, HouseholdProfile, Alert
from .serializers import (HouseholdSerializer, ForecastSerializer,
                          HouseholdProfileSerializer, AlertSerializer)
from .services import role_of, foyer_payload, operator_payload


class Scoped:
    """Un foyer ne voit que ses propres données ; analyste et admin voient tout."""
    lookup = "household"

    def get_queryset(self):
        qs = super().get_queryset()
        if role_of(self.request.user) == "foyer":
            hh = self.request.user.profile.household
            return qs.filter(**{self.lookup: hh.pk if hh else None})
        return qs


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
        if p.get("horizon") in {"1", "7"}:
            qs = qs.filter(horizon_days=int(p["horizon"]))
        if p.get("household_id"):
            qs = qs.filter(household__household_id=p["household_id"])
        return qs


class ProfileViewSet(Scoped, viewsets.ReadOnlyModelViewSet):
    queryset = HouseholdProfile.objects.select_related("household")
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
        "households": "/api/households/", "forecasts": "/api/forecasts/", "profiles": "/api/profiles/",
        "anomalies": "/api/anomalies/", "foyer": "/api/foyer/dashboard/", "operateur": "/api/operator/overview/"}})


@api_view(["GET"])
def foyer_dashboard(request):
    role = role_of(request.user)
    if role == "foyer":
        h = request.user.profile.household
    else:
        h = Household.objects.filter(household_id=request.query_params.get("household_id")).first()
    data = foyer_payload(h) if h else None
    return Response(data) if data else Response({"detail": "Aucune donnée pour ce foyer."}, status=404)


@api_view(["GET"])
def operator_overview(request):
    if role_of(request.user) not in ("analyste", "admin"):
        return Response({"detail": "Réservé aux analystes et administrateurs."}, status=403)
    data = operator_payload()
    return Response(data) if data else Response({"detail": "Aucune prévision importée."}, status=404)
