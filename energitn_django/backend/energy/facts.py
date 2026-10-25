"""
Construit le JSON de FAITS envoyé à l'assistant IA : tous les chiffres viennent de la base, jamais du LLM.
Règle d'or du projet : le code calcule, l'IA raconte.

build_facts() est une fonction PURE (listes et dictionnaires) : facile à tester sans Django.
facts_for_household() la branche sur la base de données.
"""
from datetime import timedelta


def _sum(rows, key="kwh"):
    return round(sum(r[key] for r in rows if r.get(key) is not None), 1)


def build_facts(household, daily, forecast, alerts, profile=None, bill=None, window=30):
    """
    household : {"code", "region", "persona"}
    daily     : [{"date", "kwh", "outage_hours", "tmax"}]      (passé, trié par date)
    forecast  : [{"date", "predicted", "low", "high"}]          (jours à venir)
    alerts    : [{"date", "kind", "severity", "message"}]
    bill      : dict renvoyé par le service .NET, ou None
    """
    daily = sorted((r for r in daily if r.get("kwh") is not None), key=lambda r: r["date"])
    facts = {"foyer": {"code": household["code"], "region": household["region"], "profil": profile}}
    if not daily:
        return {**facts, "donnees": "aucune consommation disponible"}
    last = daily[-1]["date"]
    cur = [r for r in daily if r["date"] > last - timedelta(days=window)]
    prev = [r for r in daily if last - timedelta(days=2 * window) < r["date"] <= last - timedelta(days=window)]
    facts["periode"] = {"du": str(cur[0]["date"]), "au": str(last)}
    facts["derniers_jours"] = {"kwh": _sum(cur), "jours": len(cur), "moyenne_par_jour": round(_sum(cur) / len(cur), 1)}
    if prev:
        avg_prev = _sum(prev) / len(prev)
        facts["jours_precedents"] = {"kwh": _sum(prev), "moyenne_par_jour": round(avg_prev, 1)}
        if avg_prev > 0:
            facts["ecart_vs_periode_precedente_pct"] = round(100 * (_sum(cur) / len(cur) - avg_prev) / avg_prev, 1)
    top = max(cur, key=lambda r: r["kwh"])
    facts["jour_le_plus_consommateur"] = {"date": str(top["date"]), "kwh": round(top["kwh"], 1), "tmax": top.get("tmax")}
    out_days = [r for r in cur if r.get("outage_hours")]
    facts["coupures"] = {"jours_concernes": len(out_days), "heures": sum(r["outage_hours"] for r in out_days)}
    if forecast:
        peak = max(forecast, key=lambda r: r["predicted"])
        facts["prevision"] = {
            "jours": [{"date": str(r["date"]), "kwh": round(r["predicted"], 1),
                       "intervalle": [round(r["low"], 1), round(r["high"], 1)]} for r in forecast],
            "pic_prevu": {"date": str(peak["date"]), "kwh": round(peak["predicted"], 1)}}
    facts["alertes_recentes"] = [{"date": str(a["date"]), "type": a["kind"], "gravite": a["severity"], "message": a["message"]}
                                 for a in sorted(alerts, key=lambda a: a["date"], reverse=True)[:5]]
    if bill:
        facts["facture_estimee"] = bill
    return facts


def facts_for_household(h, days=90, bill=None):
    """Lit la base Django et appelle build_facts."""
    from .models import Alert, DailyConsumption, Forecast
    daily_qs = list(DailyConsumption.objects.filter(household=h).order_by("-date")[:days].values("date", "kwh", "outage_hours", "tmax"))
    last = daily_qs[0]["date"] if daily_qs else None
    fc = []
    if last:
        fc = list(Forecast.objects.filter(household=h, horizon=1, date__gt=last).values("date", "predicted", "low", "high")[:7])
        if not fc:
            fc = list(Forecast.objects.filter(household=h, date__gt=last).order_by("date", "horizon")
                      .values("date", "predicted", "low", "high")[:7])
    alerts = list(Alert.objects.filter(household=h).values("date", "kind", "severity", "message")[:20])
    profile = getattr(getattr(h, "profile", None), "label", None)
    return build_facts({"code": h.code, "region": h.region.name, "persona": h.persona}, daily_qs, fc, alerts, profile, bill)
