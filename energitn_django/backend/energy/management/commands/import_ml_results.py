"""
Charge dans la base les résultats du pipeline ML (CSV et JSON) : foyers, consommation journalière, prévisions,
profils, alertes, métriques des modèles.

    python manage.py import_ml_results

Prérequis : avoir lancé generate_synthetic.py, prepare.py, train_forecast.py (h1 et h7), profiles.py, anomalies.py.
La commande est rejouable : elle remplace les données importées précédemment.
"""
import json
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from energy.paths import ml_root,data_root

from energy.models import Alert, DailyConsumption, Forecast, Household, ModelRun, Profile, Region

SEVERITY = {"haute": "high", "moyenne": "medium"}


def read_json(path):
    """Lit un JSON écrit en UTF-8 ou, sous Windows, en cp1252 (accents) : essaie les deux."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    raise CommandError(f"Impossible de lire le fichier JSON : {path}")


def num(x):
    return None if pd.isna(x) else float(x)


class Command(BaseCommand):
    help = "Importe les résultats du pipeline ML dans la base Django."

    @transaction.atomic
    def handle(self, *args, **opts):
        root = ml_root()
        data = data_root()

        syn = data / "synthetic"
        proc = data / "processed"
        mdl = root / "models"
        needed = [syn / "households.csv", proc / "daily.csv"]
        missing = [str(p) for p in needed if not p.exists()]
        if missing:
            raise CommandError(f"Fichiers introuvables : {missing}. Lancez d'abord le pipeline ML (voir le guide).")

        # 1. Régions et foyers
        hh = pd.read_csv(syn / "households.csv")
        regions = {n: Region.objects.get_or_create(name=n)[0] for n in hh.region.unique()}
        houses = {}
        for r in hh.itertuples():
            houses[r.household_id], _ = Household.objects.update_or_create(
                code=r.household_id,
                defaults=dict(region=regions[r.region], persona=r.persona, ac_coef=float(r.ac_coef), is_synthetic=True))
        self.stdout.write(f"{len(houses)} foyers")

        # 2. Consommation journalière
        d = pd.read_csv(proc / "daily.csv", parse_dates=["date"])
        DailyConsumption.objects.all().delete()
        DailyConsumption.objects.bulk_create(
            (DailyConsumption(household=houses[r.household_id], date=r.date.date(), kwh=num(r.kwh_day),
                              outage_hours=int(r.outage_h), tmax=num(r.tmax), is_holiday=bool(r.is_holiday))
             for r in d.itertuples()), batch_size=2000)
        self.stdout.write(f"{len(d)} jours de consommation")

        # 3. Métriques des modèles (ModelRun)
        runs = {}
        for name in ("forecast_h1", "forecast_h7", "anomaly"):
            f = mdl / (f"{name}_metrics.json" if name != "anomaly" else "anomaly_metrics.json")
            if f.exists():
                data = read_json(f)
                runs[name] = ModelRun.objects.create(name=name, horizon=data.get("horizon") if isinstance(data, dict) else None,
                                                     metrics=data)

        # 4. Prévisions (prévu / réel / intervalle)
        Forecast.objects.all().delete()
        for h in (1, 7):
            f = proc / f"forecast_h{h}_predictions.csv"
            if not f.exists():
                continue
            p = pd.read_csv(f, parse_dates=["date"])
            Forecast.objects.bulk_create(
                (Forecast(household=houses[r.household_id], date=r.date.date(), horizon=h, predicted=r.pred,
                          low=r.q10, high=r.q90, actual=num(r.kwh_day), model_run=runs.get(f"forecast_h{h}"))
                 for r in p.itertuples()), batch_size=2000)
            self.stdout.write(f"{len(p)} prévisions J+{h}")

        # 5. Profils
        Profile.objects.all().delete()
        f = proc / "profiles.csv"
        if f.exists():
            p = pd.read_csv(f)
            Profile.objects.bulk_create(Profile(household=houses[r.household_id], cluster=int(r.cluster), label=r.profil)
                                        for r in p.itertuples())
            self.stdout.write(f"{len(p)} profils")

        # 6. Alertes issues de la détection d'anomalies
        Alert.objects.all().delete()
        f = proc / "anomalies_flagged.csv"
        if f.exists():
            a = pd.read_csv(f, parse_dates=["date"])
            alerts = []
            for r in a.itertuples():
                if r.type == "surconsommation":
                    kind, msg = "overconsumption", f"Consommation {r.ratio:.1f} fois supérieure à la prévision ({r.kwh_day:.1f} kWh au lieu de {r.pred:.1f})."
                else:
                    kind, msg = "night_load", f"Consommation de nuit {r.night_ratio:.1f} fois supérieure à vos habitudes."
                alerts.append(Alert(household=houses[r.household_id], date=r.date.date(), kind=kind,
                                    severity=SEVERITY.get(r.gravite, "medium"), ratio=num(r.ratio), message=msg))
            Alert.objects.bulk_create(alerts, ignore_conflicts=True)
            self.stdout.write(f"{len(alerts)} alertes")
        self.stdout.write(self.style.SUCCESS("Import terminé."))
