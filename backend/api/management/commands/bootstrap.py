"""Mise en route en une commande : migrations + import des résultats ML + inférence + comptes de démonstration.
    python manage.py bootstrap
Comptes (mot de passe : EnergiTN2026!) : foyer@demo.tn · analyste@demo.tn · admin@demo.tn"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Count

from api.ml import ModelUnavailable, run_inference
from api.models import Household, UserProfile

DEMO_PASSWORD = "EnergiTN2026!"


def create_demo_accounts(stdout=None):
    U = get_user_model()
    # le foyer de démo : celui qui a le plus d'alertes (démonstration de la détection), à défaut le premier
    demo = (Household.objects.annotate(n=Count("alerts")).order_by("-n", "household_id").first())
    for email, name, role, hh, su in (("foyer@demo.tn", "Amel Ben Salah", "foyer", demo, False),
                                      ("analyste@demo.tn", "Karim Trabelsi", "analyste", None, False),
                                      ("admin@demo.tn", "Admin ÉnergiTN", "admin", None, True)):
        u, _ = U.objects.get_or_create(username=email, defaults={"email": email, "first_name": name})
        u.is_staff = u.is_superuser = su
        u.first_name = u.first_name or name
        u.set_password(DEMO_PASSWORD)
        u.save()
        UserProfile.objects.update_or_create(user=u, defaults={"role": role, "household": hh})
    if stdout:
        stdout.write(f"✓ Comptes de démo : foyer@demo.tn ({demo}), analyste@demo.tn, admin@demo.tn — mot de passe {DEMO_PASSWORD}")


class Command(BaseCommand):
    help = "Initialise ÉnergiTN : migrate, import_results, run_inference, comptes de démo"

    def handle(self, *a, **o):
        call_command("migrate", verbosity=0)
        self.stdout.write("✓ Base de données à jour")
        call_command("import_results", stdout=self.stdout)
        try:
            run_inference(stdout=self.stdout)
        except ModelUnavailable as e:
            self.stdout.write(self.style.WARNING(f"! {e}"))
        create_demo_accounts(self.stdout)
        self.stdout.write(self.style.SUCCESS("Prêt : python manage.py runserver puis http://127.0.0.1:8000/"))
