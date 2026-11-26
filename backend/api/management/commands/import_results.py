"""Importe les résultats de la chaîne ML (voir « Guide des fichiers », rôle B) :
    python manage.py import_results                      # lit ML_DATA_DIR et ML_MODELS_DIR (settings)
    python manage.py import_results --data ../data --models ../models

data/synthetic : households, weather_used, holidays_used, outages_used
data/processed : daily, forecast_h1/h7_predictions, profiles, hourly_profiles, anomalies_flagged
models         : *_metrics.json  -> table ModelRun
La vérité terrain (anomaly_day / is_anomaly) n'est PAS importée comme décision : seules les alertes produites
par anomalies.py le sont."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api import billing
from api.models import (Alert, DailyConsumption, Forecast, Holiday, Household, HouseholdProfile, ModelRun,
                        Outage, Weather)

SEVERITY = {"haute": "haute", "high": "haute", "moyenne": "moyenne", "medium": "moyenne", "basse": "basse", "low": "basse"}


def read(path, required=True, **kw):
    if not Path(path).exists():
        if required:
            raise CommandError(f"Fichier introuvable : {path} (avez-vous lancé l'étape précédente du guide ?)")
        return None
    return pd.read_csv(path, **kw)


def need(df, name, cols):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise CommandError(f"{name} : colonnes manquantes {miss}. Colonnes disponibles : {list(df.columns)}")


def num(v):
    return None if pd.isna(v) else float(v)


class Command(BaseCommand):
    help = "Importe les CSV et métriques produits par la chaîne ML"

    def add_arguments(self, p):
        p.add_argument("--data", default=None, help="dossier data/ (contient synthetic/ et processed/)")
        p.add_argument("--models", default=None, help="dossier models/ (*.joblib, *_metrics.json)")

    @transaction.atomic
    def handle(self, *a, **o):
        data = Path(o["data"] or settings.ML_DATA_DIR)
        mdir = Path(o["models"] or settings.ML_MODELS_DIR)
        syn, proc = data / "synthetic", data / "processed"
        w = self.stdout.write

        # ---- foyers
        df = read(syn / "households.csv")
        need(df, "households.csv", ["household_id", "region"])
        for r in df.to_dict("records"):
            Household.objects.update_or_create(household_id=str(r["household_id"]), defaults={
                "region": str(r["region"]), "persona": str(r.get("persona", "") or ""),
                "ac_coef": float(r.get("ac_coef", 1.0) or 1.0), "is_synthetic": bool(r.get("is_synthetic", True))})
        hh = {h.household_id: h for h in Household.objects.all()}
        w(f"✓ {len(df)} foyers")

        # ---- météo, jours fériés, coupures
        df = read(syn / "weather_used.csv", required=False)
        if df is not None:
            need(df, "weather_used.csv", ["date", "region", "tmax"])
            df = df.dropna(subset=["tmax"])
            Weather.objects.bulk_create([Weather(region=r["region"], date=pd.to_datetime(r["date"]).date(), tmax=float(r["tmax"]),
                                                 tmean=num(r.get("tmean")), source="observee") for r in df.to_dict("records")],
                                        batch_size=2000, update_conflicts=True, unique_fields=["region", "date"],
                                        update_fields=["tmax", "tmean", "source"])
            w(f"✓ {len(df)} jours de météo")
        df = read(syn / "holidays_used.csv", required=False)
        if df is not None:
            Holiday.objects.bulk_create([Holiday(date=pd.to_datetime(d).date()) for d in df["date"]], ignore_conflicts=True)
            w(f"✓ {len(df)} jours fériés")
        df = read(syn / "outages_used.csv", required=False)
        if df is not None:
            Outage.objects.all().delete()
            tz = timezone.get_current_timezone()
            Outage.objects.bulk_create([Outage(region=r["region"], start=timezone.make_aware(pd.to_datetime(r["start"]).to_pydatetime(), tz),
                                               hours=int(r["hours"])) for r in df.to_dict("records")], batch_size=2000)
            w(f"✓ {len(df)} coupures régionales")

        # ---- consommation journalière (prepare.py)
        df = read(proc / "daily.csv")
        need(df, "daily.csv", ["household_id", "date", "kwh_day"])
        df = df.dropna(subset=["kwh_day"])
        rows = [DailyConsumption(household=hh[str(r["household_id"])], date=pd.to_datetime(r["date"]).date(),
                                 kwh=round(float(r["kwh_day"]), 3), tmax=num(r.get("tmax")),
                                 outage_h=int(r.get("outage_h", 0) or 0), source="ml")
                for r in df.to_dict("records") if str(r["household_id"]) in hh]
        DailyConsumption.objects.bulk_create(rows, batch_size=2000, update_conflicts=True, unique_fields=["household", "date"],
                                             update_fields=["kwh", "tmax", "outage_h", "source"])
        w(f"✓ {len(rows)} consommations journalières")

        # ---- prévisions d'évaluation (prévu contre réel) : forecast_h*_predictions.csv
        for hz in (1, 7):
            df = read(proc / f"forecast_h{hz}_predictions.csv", required=False)
            if df is None:
                continue
            need(df, f"forecast_h{hz}_predictions.csv", ["household_id", "date", "pred"])
            actual = "kwh_day" if "kwh_day" in df.columns else ("actual" if "actual" in df.columns else None)
            Forecast.objects.filter(kind="backtest", horizon_days=hz).delete()
            rows = [Forecast(household=hh[str(r["household_id"])], target_date=pd.to_datetime(r["date"]).date(), horizon_days=hz,
                             kind="backtest", model_name=f"forecast_h{hz}", predicted_kwh=round(float(r["pred"]), 3),
                             actual_kwh=num(r[actual]) if actual else None, q10=num(r.get("q10")), q90=num(r.get("q90")))
                    for r in df.dropna(subset=["pred"]).to_dict("records") if str(r["household_id"]) in hh]
            Forecast.objects.bulk_create(rows, batch_size=2000)
            w(f"✓ {len(rows)} prévisions d'évaluation J+{hz}")

        # ---- profils (profiles.py)
        df = read(proc / "profiles.csv", required=False)
        if df is not None:
            need(df, "profiles.csv", ["household_id", "cluster", "profil"])
            hp = read(proc / "hourly_profiles.csv", required=False)
            hours = [f"h{i:02d}" for i in range(24)]
            shapes = {}
            if hp is not None:
                for r in hp.to_dict("records"):
                    shapes.setdefault(str(r["household_id"]), {})[r["season"]] = [round(float(r[c]), 4) for c in hours]
            opt = ["mean_day", "evening_share", "night_share", "summer_ratio", "load_factor", "heat_sens", "weekend_ratio"]
            # profiles.py v2 : summer_ratio = « poids de l'été » en % ; le rapport été/hiver brut est dans summer_winter_ratio
            if "summer_winter_ratio" in df.columns:
                df["summer_ratio"] = df["summer_winter_ratio"]
            for r in df.to_dict("records"):
                hid = str(r["household_id"])
                if hid in hh:
                    HouseholdProfile.objects.update_or_create(household=hh[hid], defaults={
                        "cluster": int(r["cluster"]), "profil": str(r["profil"]), "hourly": shapes.get(hid, {}),
                        **{c: num(r[c]) if c in df.columns else None for c in opt}})
            w(f"✓ {len(df)} profils")
        else:
            w(self.style.WARNING("! profiles.csv absent : lancez python profiles.py"))

        # ---- anomalies (anomalies.py)
        df = read(proc / "anomalies_flagged.csv", required=False)
        if df is not None:
            need(df, "anomalies_flagged.csv", ["household_id", "date", "type"])
            sev = "gravite" if "gravite" in df.columns else ("severity" if "severity" in df.columns else None)
            Alert.objects.filter(source="ml").delete()
            Alert.objects.bulk_create([Alert(
                household=hh.get(str(r["household_id"])), date=pd.to_datetime(r["date"]).date(), anomaly_type=str(r["type"]),
                severity=SEVERITY.get(str(r[sev]).lower(), "moyenne") if sev else "moyenne",
                kwh=num(r.get("kwh_day")), expected_kwh=num(r.get("pred")), ratio=num(r.get("ratio")),
                night_ratio=num(r.get("night_ratio")), source="ml") for r in df.to_dict("records")], ignore_conflicts=True)
            w(f"✓ {len(df)} anomalies")
        else:
            w(self.style.WARNING("! anomalies_flagged.csv absent : lancez python anomalies.py"))

        # ---- métriques des modèles -> ModelRun
        n = 0
        for name, fname in (("forecast_h1", "forecast_h1_metrics.json"), ("forecast_h7", "forecast_h7_metrics.json"),
                            ("profiles", "profiles_metrics.json"), ("anomalies", "anomaly_metrics.json")):
            p = mdir / fname
            if not p.exists():
                continue
            m = json.loads(p.read_text(encoding="utf-8"))
            if name == "anomalies" and "test" not in m:
                # anomalies.py v2 écrit directement {détecteur: scores} : on retrouve la forme attendue par l'interface.
                # Le détecteur retenu dans anomalies.py (fichier anomalies_flagged.csv) est « règles combinées ».
                m = {"test": m, "retained": next((k for k in m if k.startswith("règles combinées")), next(iter(m), None))}
            ta = m.get("trained_at")
            trained = timezone.make_aware(datetime.fromisoformat(ta)) if ta else timezone.make_aware(datetime.fromtimestamp(p.stat().st_mtime))
            ModelRun.objects.filter(name=name).update(is_active=False)
            art = f"{name}.joblib" if name.startswith("forecast") else fname
            ModelRun.objects.create(name=name, metrics=m, trained_at=trained, artifact=art, is_active=True)
            n += 1
        w(f"✓ {n} fiches de modèles (ModelRun)")
        billing.ensure_default_bands()
        w(self.style.SUCCESS("Import terminé. Données synthétiques : à présenter comme telles."))
