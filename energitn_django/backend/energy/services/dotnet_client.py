"""
Tous les appels au service ASP.NET Core sont ici, et SEULEMENT ici. Délai maximal court + repli en cas de panne :
l'interface ne doit jamais planter parce que .NET est indisponible.
Le contrat exact (noms des champs) est défini par le fichier OpenAPI du service .NET : à aligner dès le Sprint 1.
"""
import logging

import requests
from django.conf import settings

from . import alerts_engine

log = logging.getLogger(__name__)


class DotNetUnavailable(Exception):
    pass


def _post(path, payload):
    try:
        r = requests.post(f"{settings.DOTNET_URL}{path}", json=payload,
                          headers={"X-Api-Key": settings.DOTNET_API_KEY}, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.warning("Service .NET indisponible (%s) : %s", path, e)
        raise DotNetUnavailable(str(e)) from e


def estimate_bill(kwh, days=30):
    """Facture estimée par tranche. Lève DotNetUnavailable : la vue affiche alors « estimation indisponible »."""
    return _post("/api/bill/estimate", {"kwh": kwh, "days": days})


def evaluate_alert(actual, forecast, night_ratio=None):
    """Décision d'alerte par le moteur .NET ; repli sur les mêmes règles en Python si le service ne répond pas."""
    try:
        return _post("/api/alerts/evaluate", {"actual": actual, "forecast": forecast, "nightRatio": night_ratio})
    except DotNetUnavailable:
        return alerts_engine.evaluate(actual, forecast, night_ratio)
