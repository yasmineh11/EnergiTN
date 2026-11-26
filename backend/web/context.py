"""Données communes à toutes les pages : langue, sens d'écriture, menu selon le rôle, dictionnaire i18n."""
from api import ml
from api.models import Alert
from api.services import role_of
from .i18n import STR, tr

NAV = {
    "foyer": [(None, [("/foyer/", "i-home", "nav_dashboard"), ("/foyer/releves/", "i-meter", "nav_readings"),
                      ("/foyer/facture/", "i-bill", "nav_bill"), ("/foyer/profil/", "i-profile", "nav_profile"),
                      ("/foyer/assistant/", "i-chat", "nav_assistant"), ("/foyer/rapport/", "i-report", "nav_report")])],
    "analyste": [(None, [("/analyste/", "i-map", "nav_regional"), ("/analyste/profils/", "i-layers", "nav_profiles"),
                         ("/analyste/anomalies/", "i-alert", "nav_anomalies")])],
    "admin": [("nav_g_admin", [("/gestion/", "i-users", "nav_users"), ("/gestion/donnees/", "i-data", "nav_data"),
                               ("/gestion/modeles/", "i-model", "nav_models"), ("/gestion/referentiel/", "i-settings", "nav_reference")]),
              ("nav_g_analysis", [("/analyste/", "i-map", "nav_regional"), ("/analyste/profils/", "i-layers", "nav_profiles"),
                                  ("/analyste/anomalies/", "i-alert", "nav_anomalies")])],
}


def shell(request):
    lang = "ar" if request.COOKIES.get("lang") == "ar" else "fr"
    ctx = {"lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "i18n": {k: v[1] if lang == "ar" else v[0] for k, v in STR.items()}}
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return ctx
    role = role_of(user)
    open_alerts = 0
    if role == "foyer" and getattr(user, "profile", None) and user.profile.household_id:
        open_alerts = Alert.objects.filter(household_id=user.profile.household_id, is_resolved=False).count()
    nav = []
    for title, items in NAV.get(role, []):
        nav.append({"title": tr(title, lang) if title else None, "items": [
            {"url": u, "icon": ic, "label": tr(k, lang), "active": request.path == u or (u not in ("/foyer/", "/analyste/", "/gestion/") and request.path.startswith(u)),
             "count": open_alerts if u == "/foyer/profil/" else 0} for u, ic, k in items]})
    name = user.first_name or user.username.split("@")[0]
    space = "analyste" if request.path.startswith("/analyste") else "admin" if request.path.startswith("/gestion") else "foyer"
    current = next((it for g in nav for it in g["items"] if it["active"]), None)
    ctx.update({"ml_ok": ml.models_available(), "space_label": tr(f"eyebrow_{space}", lang),
                "page_label": current["label"] if current else ""})
    ctx.update({"nav": nav, "display_name": name, "initials": "".join(p[0] for p in name.split()[:2]).upper() or "?",
                "role_label": tr(f"role_{role}", lang) if role else ""})
    return ctx
