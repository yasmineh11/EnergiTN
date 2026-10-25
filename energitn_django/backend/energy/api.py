from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import facts as facts_mod
from .models import Alert, DailyConsumption, Forecast, Household
from .services import dotnet_client, llm_client


def household_for(request, code):
    """Un foyer ne voit que SES données ; analyste et administrateur voient tout."""
    h = get_object_or_404(Household.objects.select_related("region"), code=code)
    role = getattr(request.user, "role", "household")
    if request.user.is_superuser or role in ("analyst", "admin") or h.owner_id == request.user.id:
        return h
    raise PermissionDenied("Ce foyer ne vous appartient pas.")


@api_view(["GET"])
def consumption(request, code):
    """?period=day|week|month&days=90"""
    h = household_for(request, code)
    period, days = request.GET.get("period", "day"), int(request.GET.get("days", 90))
    qs = DailyConsumption.objects.filter(household=h)
    last = qs.order_by("-date").values_list("date", flat=True).first()
    if last is None:
        return Response([])
    qs = qs.filter(date__gt=last - timedelta(days=days))
    if period == "day":
        data = qs.values("date", "kwh", "outage_hours", "tmax")
    else:
        trunc = TruncWeek if period == "week" else TruncMonth
        data = qs.annotate(period=trunc("date")).values("period").annotate(kwh=Sum("kwh")).order_by("period")
    return Response(list(data))


@api_view(["GET"])
def forecast(request, code):
    """?horizon=1&limit=30 -> prévu, intervalle (indicateur de confiance) et réel quand il est connu."""
    h = household_for(request, code)
    qs = Forecast.objects.filter(household=h, horizon=int(request.GET.get("horizon", 1))).order_by("-date")
    rows = list(qs.values("date", "predicted", "low", "high", "actual")[:int(request.GET.get("limit", 30))])
    return Response(rows[::-1])


@api_view(["GET"])
def profile(request, code):
    h = household_for(request, code)
    p = getattr(h, "profile", None)
    return Response({"cluster": p.cluster, "label": p.label} if p else {})


@api_view(["GET"])
def alerts(request, code):
    h = household_for(request, code)
    return Response(list(Alert.objects.filter(household=h).values("date", "kind", "severity", "message", "is_read")[:50]))


def _last_30_days_kwh(h):
    last = DailyConsumption.objects.filter(household=h).order_by("-date").values_list("date", flat=True).first()
    if last is None:
        return 0.0
    agg = DailyConsumption.objects.filter(household=h, date__gt=last - timedelta(days=30)).aggregate(s=Sum("kwh"))
    return round(agg["s"] or 0.0, 1)


@api_view(["GET"])
def bill(request, code):
    h = household_for(request, code)
    kwh = _last_30_days_kwh(h)
    try:
        return Response({"kwh": kwh, "estimation": dotnet_client.estimate_bill(kwh, 30)})
    except dotnet_client.DotNetUnavailable:
        return Response({"kwh": kwh, "detail": "Estimation de facture momentanément indisponible."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["POST"])
def assistant(request, code):
    """Corps : {"question": "..."} -> {"answer": "..."} ; l'assistant ne voit que les faits calculés par le système."""
    h = household_for(request, code)
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"detail": "Question vide."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        bill_info = dotnet_client.estimate_bill(_last_30_days_kwh(h), 30)
    except dotnet_client.DotNetUnavailable:
        bill_info = None
    facts = facts_mod.facts_for_household(h, bill=bill_info)
    try:
        return Response({"answer": llm_client.answer(question, facts)})
    except Exception:                                                       # clé absente, quota, réseau...
        return Response({"detail": "L'assistant est momentanément indisponible."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
