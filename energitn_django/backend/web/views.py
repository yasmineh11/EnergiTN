import io, json, re
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from api.models import Household, UserProfile
from api.services import role_of, foyer_payload, operator_payload, admin_payload, users_payload

U = get_user_model()
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def landing(user):
    return {"foyer": "/foyer/", "analyste": "/operateur/", "admin": "/gestion/"}.get(role_of(user), "/login/")


def home(request):
    return redirect(landing(request.user))


def login_view(request):
    err = ""
    if request.method == "POST":
        email = request.POST.get("username", "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password", ""))
        if user:
            login(request, user)
            return redirect(landing(user))
        err = "bad_credentials"
    return render(request, "auth.html", {"mode": "login", "error": err})


def register_view(request):
    err, email = "", ""
    if request.method == "POST":
        f = request.POST
        name, email, pw = f.get("name", "").strip(), f.get("username", "").strip().lower(), f.get("password", "")
        if not name: err = "e_name"
        elif not EMAIL.match(email): err = "e_mail"
        elif len(pw) < 6: err = "e_pw"
        elif pw != f.get("password2", ""): err = "e_match"
        elif U.objects.filter(username=email).exists(): err = "exists"
        else:
            user = U.objects.create_user(username=email, email=email, password=pw, first_name=name)
            # Prototype : le nouveau foyer reçoit le premier foyer simulé encore libre
            hh = Household.objects.filter(userprofile__isnull=True).order_by("household_id").first()
            UserProfile.objects.create(user=user, role="foyer", household=hh)
            login(request, user)
            return redirect("/foyer/")
    return render(request, "auth.html", {"mode": "register", "error": err, "email": email})


def logout_view(request):
    logout(request)
    return redirect("/login/")


@login_required
def foyer_page(request):
    if role_of(request.user) != "foyer":
        return redirect(landing(request.user))
    hh = request.user.profile.household
    data = foyer_payload(hh) if hh else None
    return render(request, "foyer.html" if data else "empty.html", {"data": data})


@login_required
def operateur_page(request):
    if role_of(request.user) not in ("analyste", "admin"):
        return redirect(landing(request.user))
    data = operator_payload()
    return render(request, "operateur.html" if data else "empty.html", {"data": data})


@login_required
def gestion_page(request):
    if role_of(request.user) != "admin":
        return redirect(landing(request.user))
    return render(request, "admin.html", {"data": admin_payload()})


@login_required
@require_POST
def gestion_user(request):
    """Créer ou modifier un compte (UC09). Réservé aux administrateurs."""
    if role_of(request.user) != "admin":
        return JsonResponse({"error": "forbidden"}, status=403)
    b = json.loads(request.body or "{}")
    role = b.get("role", "foyer")
    hh = Household.objects.filter(household_id=b.get("household") or None).first()
    if role not in ("foyer", "analyste", "admin"):
        return JsonResponse({"error": "e_role"}, status=400)
    if b.get("id"):
        u = U.objects.filter(pk=b["id"]).first()
        if not u:
            return JsonResponse({"error": "e_none"}, status=404)
        if u == request.user and (role != "admin" or not b.get("active", True)):
            return JsonResponse({"error": "e_self"}, status=400)
        u.is_active = bool(b.get("active", True)); u.save()
    else:
        email, pw = (b.get("email") or "").strip().lower(), b.get("password", "")
        if not EMAIL.match(email): return JsonResponse({"error": "e_mail"}, status=400)
        if len(pw) < 6: return JsonResponse({"error": "e_pw"}, status=400)
        if U.objects.filter(username=email).exists(): return JsonResponse({"error": "exists"}, status=400)
        u = U.objects.create_user(username=email, email=email, password=pw, first_name=(b.get("name") or "").strip())
    UserProfile.objects.update_or_create(user=u, defaults={"role": role, "household": hh if role == "foyer" else None})
    return JsonResponse({"ok": True, "users": users_payload()})


@login_required
@require_POST
def gestion_action(request):
    """Importer les résultats ML (UC14) ou régénérer les données synthétiques de démo (UC15)."""
    if role_of(request.user) != "admin":
        return JsonResponse({"error": "forbidden"}, status=403)
    action, out = json.loads(request.body or "{}").get("action"), io.StringIO()
    try:
        if action == "import":
            d = settings.ML_DATA_DIR
            call_command("import_results", synthetic=str(d / "synthetic"), processed=str(d / "processed"), stdout=out)
        elif action == "seed":
            call_command("seed_demo", reset=True, stdout=out)
        else:
            return JsonResponse({"error": "e_action"}, status=400)
    except CommandError as e:
        return JsonResponse({"ok": False, "log": str(e)})
    return JsonResponse({"ok": True, "log": out.getvalue(), "data": admin_payload()})
