"""Pages et actions des trois espaces. Contrôle d'accès par rôle (NF07) : un foyer ne voit que ses données."""
import csv
import io
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, password_validation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from api import billing, ml, pipeline
from api.facts import DISCLAIMER, MONTHS, answer, available_months, household_facts, monthly_report
from api.management.commands.bootstrap import DEMO_PASSWORD
from api.models import PERSONAS, Alert, ChatMessage, Forecast, Household, HouseholdProfile, TariffBand, UserProfile, Weather
from api.regions import BY_ID, REGIONS
from api.services import (admin_overview, analyst_anomalies, analyst_forecast, analyst_profiles, chat_history,
                          datasets_payload, foyer_alerts, foyer_dashboard, foyer_readings, households_payload,
                          models_payload, pipeline_payload, role_of, tariff_payload, users_payload)

from .i18n import tr

U = get_user_model()
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HOME = {"foyer": "/foyer/", "analyste": "/analyste/", "admin": "/gestion/"}


def lang_of(request):
    return "ar" if request.COOKIES.get("lang") == "ar" else "fr"


def landing_url(user):
    return HOME.get(role_of(user), "/login/")


def role_required(*roles, api=False):
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **kw):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "e_auth"}, status=401) if api else redirect(f"/login/?next={request.path}")
            if role_of(request.user) not in roles:
                return JsonResponse({"error": "forbidden"}, status=403) if api else redirect(landing_url(request.user))
            return view(request, *a, **kw)
        return wrapper
    return deco


def household_of(request):
    p = getattr(request.user, "profile", None)
    return p.household if p else None


def body(request):
    try:
        return json.loads(request.body or "{}")
    except ValueError:
        return {}


def hero_data():
    """Données réelles du foyer de démo pour l'accueil (prévision issue des modèles .joblib)."""
    from api.facts import model_quality
    h = (UserProfile.objects.filter(user__username="foyer@demo.tn").select_related("household").first() or None)
    h = h.household if h and h.household else Household.objects.filter(forecasts__kind="future").first()
    fc = []
    who = ""
    if h:
        fc = [{"date": f.target_date.isoformat(), "pred": round(f.predicted_kwh, 1), "q10": round(f.q10, 1), "q90": round(f.q90, 1),
               "tmax": f.tmax_used} for f in Forecast.objects.filter(household=h, kind="future").order_by("target_date")]
        reg = h.region_info or {}
        who = f"{h.household_id} · {reg.get('fr', h.region)}"
    q = model_quality()
    t1 = (q.get("forecast_h1") or {}).get("test", {})
    an = q.get("anomalies") or {}
    ret = (an.get("test") or {}).get(an.get("retained")) or {}
    return {"forecast": fc, "who": who, "n_households": Household.objects.count(),
            "mape": (t1.get("ensemble") or {}).get("MAPE_%"), "base": (t1.get("baseline (même jour sem. dernière)") or {}).get("MAPE_%"),
            "k": (q.get("profiles") or {}).get("k"), "f1": ret.get("F1"), "precision": ret.get("precision"), "recall": ret.get("rappel")}


# =========================================================================== public
def home(request):
    if request.user.is_authenticated and role_of(request.user):
        return redirect(landing_url(request.user))
    return render(request, "landing.html", {"hero": hero_data()})


def set_lang(request, code):
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    r = redirect(nxt)
    r.set_cookie("lang", "ar" if code == "ar" else "fr", max_age=365 * 24 * 3600, samesite="Lax")
    return r


def demo_ctx():
    return {"hero": hero_data(), "demo_password": DEMO_PASSWORD if getattr(settings, "DEMO_ACCOUNTS", settings.DEBUG) else None}


def login_view(request):
    err, email = "", ""
    nxt = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        email = request.POST.get("username", "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password", ""))
        if user:
            login(request, user)
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect(landing_url(user))
        err = "bad_credentials"
    return render(request, "auth.html", {"mode": "login", "error": err, "email": email, "next": nxt, **demo_ctx()})


def register_view(request):
    err, pw_errors, form, step = "", [], {}, 1
    if request.method == "POST":
        f = request.POST
        form = {k: f.get(k, "").strip() for k in ("name", "username", "mode", "region", "persona", "consent")}
        name, email, pw = form["name"], form["username"].lower(), f.get("password", "")
        if not name:
            err = "e_name"
        elif not EMAIL.match(email):
            err = "e_mail"
        elif pw != f.get("password2", ""):
            err = "e_match"
        elif U.objects.filter(username=email).exists():
            err = "exists"
        else:
            try:
                password_validation.validate_password(pw, U(username=email, email=email, first_name=name))
            except ValidationError as e:
                pw_errors = list(e.messages)
        if not err and not pw_errors:
            step = 2
            reg = BY_ID.get(form["region"])
            if not reg:
                err = "e_region"
            elif not form["consent"]:
                err = "e_consent"
        if not err and not pw_errors:
            with transaction.atomic():
                user = U.objects.create_user(username=email, email=email, password=pw, first_name=name)
                if form["mode"] == "own":
                    n = Household.objects.filter(household_id__startswith="U").count() + 1
                    while Household.objects.filter(household_id=f"U{n:03d}").exists():
                        n += 1
                    try:
                        ac = float(f.get("ac", "1.0"))
                    except ValueError:
                        ac = 1.0
                    hh = Household.objects.create(household_id=f"U{n:03d}", region=reg["ml"],
                                                  persona=form["persona"] if form["persona"] in PERSONAS else "couple_actif",
                                                  ac_coef=min(max(ac, 0.5), 1.5), is_synthetic=False)
                else:
                    # foyer simulé encore libre, de préférence dans la région choisie
                    free = Household.objects.filter(userprofile__isnull=True, is_synthetic=True)
                    hh = free.filter(region=reg["ml"]).order_by("household_id").first() or free.order_by("household_id").first()
                UserProfile.objects.create(user=user, role="foyer", household=hh)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, tr("welcome", lang_of(request)))
            return redirect("/foyer/")
        if pw_errors:
            step = 1
    return render(request, "auth.html", {"mode": "register", "error": err, "pw_errors": pw_errors, "form": form, "step": step,
                                         "regions": REGIONS, "personas": [(k, v[1] if lang_of(request) == "ar" else v[0]) for k, v in PERSONAS.items()],
                                         **demo_ctx()})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("/")


def csrf_failure(request, reason=""):
    """Jeton CSRF périmé (connexion dans un autre onglet, bouton « retour »…) : au lieu de la page
    technique de Django, on déconnecte proprement (/logout/) ou on recharge la page avec un message clair."""
    lang = lang_of(request)
    if request.path.rstrip("/") == "/logout":
        logout(request)
        return redirect("/login/")
    wants_json = (request.content_type == "application/json" or request.path.startswith("/api/")
                  or "application/json" in request.headers.get("Accept", ""))
    if wants_json:
        return JsonResponse({"error": "e_csrf", "detail": tr("csrf_expired", lang)}, status=403)
    messages.error(request, tr("csrf_expired", lang))
    ref = request.headers.get("Referer", "")
    host = request.get_host()
    back = ref.split(host, 1)[1] if host in ref else request.path
    return redirect(back or "/")


# =========================================================================== foyer
def _foyer_ctx(request):
    h = household_of(request)
    return h, (household_facts(h) if h else {"has_data": False})


@role_required("foyer")
def foyer_page(request):
    h = household_of(request)
    data = foyer_dashboard(h) if h else {"facts": {"has_data": False}}
    return render(request, "foyer/dashboard.html", {"data": data, "facts": data["facts"]})


def _parse_kwh(v):
    try:
        x = float(str(v).replace(",", ".").strip())
    except ValueError:
        return None
    return x if 0 <= x <= 200 else None


def _parse_date(v):
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


@role_required("foyer")
def foyer_releves(request):
    h = household_of(request)
    L = lang_of(request)
    if not h:
        messages.error(request, tr("no_household", L))
        return redirect("/foyer/")
    result, errors = None, []
    today = timezone.localdate()
    if request.method == "POST":
        items = []
        if request.POST.get("action") == "manual":
            d, k = _parse_date(request.POST.get("date", "")), _parse_kwh(request.POST.get("kwh", ""))
            if not d or d > today:
                errors.append(tr("e_date", L))
            if k is None:
                errors.append(tr("e_kwh", L))
            if not errors:
                items = [(d, k)]
        else:
            f = request.FILES.get("file")
            if not f or f.size > 2_000_000:
                errors.append(tr("e_file", L))
            else:
                text = f.read().decode("utf-8-sig", errors="replace")
                dialect = csv.Sniffer().sniff(text[:1024], delimiters=",;\t") if text.strip() else csv.excel
                for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
                    if not row or (i == 0 and not _parse_date(row[0])):
                        continue
                    d, k = _parse_date(row[0]), _parse_kwh(row[1] if len(row) > 1 else "")
                    if not d or k is None or d > today:
                        errors.append(tr("e_line", L).format(n=i + 1))
                        continue
                    items.append((d, k))
                if len(items) > 1000:
                    errors.append(tr("e_too_many", L))
                    items = []
        if items:
            res = ml.save_readings(h, items, source="saisie" if request.POST.get("action") == "manual" else "import")
            result = {"saved": res["saved"], "forecasts": res["forecasts"],
                      "alerts": [{"date": f"{a.date.day} {MONTHS[L][a.date.month - 1]}", "kwh": f"{a.kwh:.1f}",
                                  "expected_kwh": f"{a.expected_kwh:.1f}"} for a in res["alerts"]]}
            errors = errors[:5]
    last = foyer_readings(h)["last"]
    nd = (date.fromisoformat(last) + timedelta(days=1)) if last else today
    return render(request, "foyer/releves.html", {"data": foyer_readings(h), "result": result, "errors": errors[:8],
                                                  "next_date": min(nd, today).isoformat(), "today": today.isoformat()})


@role_required("foyer")
def readings_template(request):
    r = HttpResponse(content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="releves_energitn.csv"'
    w = csv.writer(r)
    w.writerow(["date", "kwh"])
    for i in range(1, 4):
        w.writerow([(timezone.localdate() - timedelta(days=4 - i)).isoformat(), "12.5"])
    return r


@role_required("foyer")
def foyer_facture(request):
    h = household_of(request)
    if not h:
        return redirect("/foyer/")
    d = foyer_dashboard(h)
    if not d["facts"].get("has_data"):
        return redirect("/foyer/releves/")
    return render(request, "foyer/facture.html", {"data": {"facts": d["facts"], "months": d["months"]}})


@role_required("foyer")
def foyer_profil(request):
    h = household_of(request)
    if not h:
        return redirect("/foyer/")
    prof = getattr(h, "profile", None)
    return render(request, "foyer/profil.html", {"data": {"facts": household_facts(h), "alerts": foyer_alerts(h),
                                                          "hourly": prof.hourly if prof else {}}})


@role_required("foyer", api=True)
@require_POST
def resolve_alert(request):
    h = household_of(request)
    n = Alert.objects.filter(pk=body(request).get("id"), household=h).update(is_resolved=True) if h else 0
    return JsonResponse({"ok": bool(n)} if n else {"error": "e_none"}, status=200 if n else 404)


@role_required("foyer")
def foyer_assistant(request):
    h, f = _foyer_ctx(request)
    return render(request, "foyer/assistant.html", {"data": {"facts": f, "history": chat_history(request.user)},
                                                    "llm": bool(settings.ANTHROPIC_API_KEY)})


@role_required("foyer", api=True)
@require_POST
def assistant_ask(request):
    q = str(body(request).get("q", "")).strip()[:500]
    if not q:
        return JsonResponse({"error": "e_empty"}, status=400)
    h, f = _foyer_ctx(request)
    L = lang_of(request)
    if re.search(r"[؀-ۿ]", q):          # question en arabe : réponse en arabe
        L = "ar"
    hist = [{"role": m["role"], "content": m["content"]} for m in chat_history(request.user, 6)]
    text, engine = answer(q, f, L, hist)
    ChatMessage.objects.create(user=request.user, role="user", content=q, lang=L)
    ChatMessage.objects.create(user=request.user, role="assistant", content=text, lang=L, engine=engine)
    return JsonResponse({"answer": text, "engine": engine, "disclaimer": DISCLAIMER[L]})


@role_required("foyer")
@require_POST
def assistant_clear(request):
    ChatMessage.objects.filter(user=request.user).delete()
    return redirect("/foyer/assistant/")


@role_required("foyer")
def foyer_rapport(request):
    h = household_of(request)
    if not h:
        return redirect("/foyer/")
    months = available_months(h)
    cur = request.GET.get("m") if request.GET.get("m") in months else (months[0] if months else None)
    # par défaut : dernier mois complet
    if not request.GET.get("m") and len(months) > 1:
        rep0 = monthly_report(h, months[0], lang_of(request))
        cur = months[0] if rep0 and rep0["complete"] else months[1]
    rep = monthly_report(h, cur, lang_of(request)) if cur else None
    reg = h.region_info or {}
    who = f"{h.household_id} · {reg.get('ar' if lang_of(request) == 'ar' else 'fr', h.region)}"
    return render(request, "foyer/rapport.html", {"months": months[:18], "current": cur, "report": rep, "facts_who": who})


# =========================================================================== analyste
@role_required("analyste", "admin")
def analyste_previsions(request):
    return render(request, "analyste/previsions.html", {"data": analyst_forecast()})


@role_required("analyste", "admin")
def analyste_profils(request):
    return render(request, "analyste/profils.html", {"data": analyst_profiles()})


@role_required("analyste", "admin")
def analyste_anomalies(request):
    return render(request, "analyste/anomalies.html", {"data": analyst_anomalies()})


# =========================================================================== administration
def _users_data():
    return {"users": users_payload(), "households": households_payload(), "overview": admin_overview()}


@role_required("admin")
def gestion_page(request):
    return render(request, "gestion/utilisateurs.html", {"data": _users_data()})


@role_required("admin")
def gestion_donnees(request):
    return render(request, "gestion/donnees.html", {"data": {"datasets": datasets_payload(), "pipeline": pipeline_payload()}})


@role_required("admin")
def gestion_modeles(request):
    from api import insights
    data = models_payload()
    data["health"] = insights.ml_health()
    data["drift"] = insights.drift_report()
    data["households"] = list(Household.objects.order_by("household_id").values_list("household_id", "region"))
    return render(request, "gestion/modeles.html", {"data": data})


@role_required("admin")
def gestion_referentiel(request):
    return render(request, "gestion/referentiel.html", {"data": tariff_payload()})


@role_required("admin", api=True)
@require_POST
def gestion_user(request):
    """UC09 : créer un compte, changer le rôle, lier un foyer, activer/désactiver."""
    b = body(request)
    role = b.get("role", "foyer")
    if role not in ("foyer", "analyste", "admin"):
        return JsonResponse({"error": "e_role"}, status=400)
    hh = Household.objects.filter(household_id=b.get("household") or None).first() if role == "foyer" else None
    if hh and UserProfile.objects.filter(household=hh).exclude(user_id=b.get("id")).exists():
        return JsonResponse({"error": "e_taken"}, status=400)
    if b.get("id"):
        u = U.objects.filter(pk=b["id"]).first()
        if not u:
            return JsonResponse({"error": "e_none"}, status=404)
        active = bool(b.get("active", True))
        if u == request.user and (role != "admin" or not active):
            return JsonResponse({"error": "e_self"}, status=400)
        u.is_active = active
        u.is_staff = u.is_superuser = role == "admin"
        u.save()
    else:
        email, pw = (b.get("email") or "").strip().lower(), b.get("password", "")
        if not EMAIL.match(email):
            return JsonResponse({"error": "e_mail"}, status=400)
        if U.objects.filter(username=email).exists():
            return JsonResponse({"error": "exists"}, status=400)
        try:
            password_validation.validate_password(pw, U(username=email, email=email))
        except ValidationError as e:
            return JsonResponse({"error": "e_pw", "messages": list(e.messages)}, status=400)
        u = U.objects.create_user(username=email, email=email, password=pw, first_name=(b.get("name") or "").strip(),
                                  is_staff=role == "admin", is_superuser=role == "admin")
    UserProfile.objects.update_or_create(user=u, defaults={"role": role, "household": hh})
    return JsonResponse({"ok": True, "data": _users_data()})


@role_required("admin", api=True)
@require_POST
def gestion_pipeline(request):
    b = body(request)
    steps = [s for s in b.get("steps", []) if s in pipeline.STEPS]
    if not steps:
        return JsonResponse({"error": "e_steps"}, status=400)
    run = pipeline.start(request.user, steps, {"households": b.get("households", 30), "seed": b.get("seed", 42)})
    if not run:
        return JsonResponse({"error": "e_busy"}, status=409)
    return JsonResponse({"run": pipeline_payload()["runs"][0]})


@role_required("admin", api=True)
def gestion_pipeline_status(request, pk):
    runs = [r for r in pipeline_payload()["runs"] if r["id"] == pk]
    if not runs:
        return JsonResponse({"error": "e_none"}, status=404)
    return JsonResponse({"run": runs[0], "datasets": datasets_payload()})


@role_required("admin", api=True)
@require_POST
def gestion_meteo(request):
    """Import d'une prévision météo (date, region, tmax) : remplace la normale climatique dans l'inférence."""
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "e_file"}, status=400)
    rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig", errors="replace"))))
    from api.regions import region_of
    n = 0
    for r in rows:
        reg, d = region_of(r.get("region")), _parse_date(r.get("date", ""))
        try:
            t = float(str(r.get("tmax", "")).replace(",", "."))
        except ValueError:
            continue
        if reg and d:
            Weather.objects.update_or_create(region=reg["ml"], date=d, defaults={"tmax": t, "source": "prevision"})
            n += 1
    if not n:
        return JsonResponse({"error": "e_weather", "message": "Colonnes attendues : date, region, tmax"}, status=400)
    res = ml.run_inference()
    return JsonResponse({"ok": True, "rows": n, "forecasts": res["forecasts"]})


@role_required("admin", api=True)
@require_POST
def gestion_profils(request):
    names = body(request).get("names", {})
    for c, name in names.items():
        name = str(name).strip()[:150]
        if name:
            HouseholdProfile.objects.filter(cluster=int(c)).update(profil=name)
    return JsonResponse({"ok": True})


@role_required("admin", api=True)
@require_POST
def gestion_tarifs(request):
    bands = body(request).get("bands", [])
    clean = []
    try:
        for b in bands:
            label = str(b.get("label", "")).strip()[:80]
            price = Decimal(str(b.get("price", "")).replace(",", "."))
            mx = int(b["max"]) if str(b.get("max", "")).strip() else None
            if not label or price < 0:
                raise ValueError
            clean.append((label, mx, price))
    except (ValueError, InvalidOperation, TypeError):
        return JsonResponse({"error": "e_tariff"}, status=400)
    if not clean or sum(m is None for _, m, _ in clean) != 1:
        return JsonResponse({"error": "e_tariff_last"}, status=400)
    clean.sort(key=lambda x: (x[1] is None, x[1] or 0))
    with transaction.atomic():
        TariffBand.objects.all().delete()
        TariffBand.objects.bulk_create([TariffBand(label=l, max_kwh_year=m, price_dt=p, order=i) for i, (l, m, p) in enumerate(clean)])
    return JsonResponse({"ok": True})


def not_found(request, exception=None):
    return render(request, "404.html", status=404)
