"""Tâche « nocturne » du guide : charge forecast_h1.joblib et forecast_h7.joblib et calcule les prévisions
des 7 jours qui suivent le dernier relevé de chaque foyer (table Forecast, kind=future).
    python manage.py run_inference [--household H001]
À planifier chaque nuit (cron Linux : 0 2 * * * ; Windows : Planificateur de tâches)."""
from django.core.management.base import BaseCommand, CommandError

from api.ml import ModelUnavailable, run_inference
from api.models import Household


class Command(BaseCommand):
    help = "Calcule les prévisions futures avec les modèles .joblib"

    def add_arguments(self, p):
        p.add_argument("--household", default=None)

    def handle(self, *a, **o):
        hs = Household.objects.filter(household_id=o["household"]) if o["household"] else None
        try:
            run_inference(hs, stdout=self.stdout)
        except ModelUnavailable as e:
            raise CommandError(str(e))
