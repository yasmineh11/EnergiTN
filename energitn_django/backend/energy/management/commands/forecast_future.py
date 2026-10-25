"""
Prévisions "en production" pour les prochains jours, avec le modèle sauvegardé (ml/inference.py).

    python manage.py forecast_future --as-of 2026-10-22 --days 7

--as-of : dernier jour connu (en démo : une date de votre jeu de données ; les jours suivants servent alors aussi de test,
          car la colonne "actual" est remplie si le réel existe).
Météo : fichier data/synthetic/weather_used.csv (démo). En production : remplacer par une prévision météo (Open-Meteo).
"""
import sys
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from energy.models import DailyConsumption, Forecast, Household


class Command(BaseCommand):
    help = "Prévoit la consommation des prochains jours pour tous les foyers."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", required=True, help="dernier jour connu, AAAA-MM-JJ")
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **o):
        root = Path(settings.ML_ROOT)
        sys.path.insert(0, str(root / "ml"))
        from inference import forecast_next_days, load_bundle            # ml/inference.py

        model_file = root / "models" / "forecast_h1.joblib"
        if not model_file.exists():
            raise CommandError("models/forecast_h1.joblib introuvable : lancez train_forecast.py --horizon 1")
        as_of = pd.Timestamp(o["as_of"])
        rows = (DailyConsumption.objects.filter(date__lte=as_of.date())
                .values("household__code", "date", "kwh", "household__region__name", "household__persona", "household__ac_coef"))
        hist = pd.DataFrame(list(rows)).rename(columns={"household__code": "household_id", "kwh": "kwh_day",
                                                        "household__region__name": "region",
                                                        "household__persona": "persona", "household__ac_coef": "ac_coef"})
        if hist.empty:
            raise CommandError("Aucune consommation en base : lancez d'abord import_ml_results.")
        hist["date"] = pd.to_datetime(hist["date"])
        weather = pd.read_csv(root / "data" / "synthetic" / "weather_used.csv", parse_dates=["date"])
        holidays = set(pd.read_csv(root / "data" / "synthetic" / "holidays_used.csv", parse_dates=["date"]).date)
        out = forecast_next_days(hist, weather, holidays, load_bundle(model_file), days=o["days"])
        if out.empty:
            raise CommandError("Aucune prévision produite : la météo couvre-t-elle les jours après --as-of ?")

        houses = {h.code: h for h in Household.objects.all()}
        actual = {(c.household_id, c.date): c.kwh for c in
                  DailyConsumption.objects.filter(date__in=[d.date() for d in out.date.unique()])}
        Forecast.objects.filter(date__in=[d.date() for d in out.date.unique()],
                                horizon__in=list(out.horizon.unique())).delete()      # remplace les anciennes prévisions
        Forecast.objects.bulk_create(
            Forecast(household=houses[r.household_id], date=r.date.date(), horizon=int(r.horizon), predicted=r.predicted,
                     low=r.low, high=r.high, actual=actual.get((houses[r.household_id].id, r.date.date())))
            for r in out.itertuples())
        self.stdout.write(self.style.SUCCESS(f"{len(out)} prévisions enregistrées ({out.date.min().date()} -> {out.date.max().date()})."))
