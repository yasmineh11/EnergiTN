"""Importe les résultats de la chaîne ML (voir « Guide des fichiers »).
    python manage.py import_results --synthetic ../data/synthetic --processed ../data/processed
Les noms de colonnes exacts ne sont pas garantis par le guide : le script teste plusieurs noms
courants et, sinon, s'arrête en listant les colonnes disponibles (adaptez alors CANDIDATES)."""
from pathlib import Path
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from api.models import Household, DailyConsumption, Forecast, HouseholdProfile, Alert

CANDIDATES = {
    "kwh": ["kwh_day", "kwh_total", "daily_kwh", "kwh", "consumption_kwh"],
    "tmax": ["tmax", "temp_max", "temperature_max", "temperature"],
    "date": ["date", "target_date", "day"],
    "pred": ["y_pred", "pred", "predicted_kwh", "forecast", "prediction"],
    "actual": ["y_true", "actual", "actual_kwh", "real", "kwh"],
    "q10": ["q10", "y_q10", "pred_q10", "lower"],
    "q90": ["q90", "y_q90", "pred_q90", "upper"],
    "type": ["type", "anomaly_type", "detector"],
    "severity": ["severity", "gravite", "gravité"],
}


def pick(df, key, required=True):
    for c in CANDIDATES[key]:
        if c in df.columns:
            return c
    if required:
        raise CommandError(f"Colonne « {key} » introuvable. Colonnes disponibles : {list(df.columns)}")
    return None


def read(path):
    if not Path(path).exists():
        raise CommandError(f"Fichier introuvable : {path}")
    return pd.read_csv(path)


def num(v):
    return None if pd.isna(v) else float(v)


class Command(BaseCommand):
    help = "Importe households, daily, prévisions, profils et anomalies"

    def add_arguments(self, p):
        p.add_argument("--synthetic", default="../data/synthetic")
        p.add_argument("--processed", default="../data/processed")

    def handle(self, *a, **o):
        syn, proc = Path(o["synthetic"]), Path(o["processed"])
        df = read(syn / "households.csv")
        for c in ("household_id", "region"):
            if c not in df.columns:
                raise CommandError(f"households.csv : colonne {c} absente ({list(df.columns)})")
        for r in df.to_dict("records"):
            Household.objects.update_or_create(household_id=str(r["household_id"]), defaults={
                "region": str(r["region"]), "persona": str(r.get("persona", ""))})
        hh = {h.household_id: h for h in Household.objects.all()}
        self.stdout.write(f"{len(hh)} foyers")

        df = read(proc / "daily.csv")
        dc, kc, tc = pick(df, "date"), pick(df, "kwh"), pick(df, "tmax", False)
        rows = [DailyConsumption(household=hh[str(r["household_id"])], date=pd.to_datetime(r[dc]).date(),
                                 kwh=float(r[kc]), tmax=num(r[tc]) if tc else None)
                for r in df.dropna(subset=[kc]).to_dict("records") if str(r["household_id"]) in hh]
        DailyConsumption.objects.bulk_create(rows, batch_size=2000, update_conflicts=True,
                                             unique_fields=["household", "date"], update_fields=["kwh", "tmax"])
        self.stdout.write(f"{len(rows)} consommations journalières")

        for hz in (1, 7):
            f = proc / f"forecast_h{hz}_predictions.csv"
            if not f.exists():
                continue
            df = read(f)
            dc, pc = pick(df, "date"), pick(df, "pred")
            ac = next((c for c in CANDIDATES["actual"] if c in df.columns and c != pc), None)
            q10, q90 = pick(df, "q10", False), pick(df, "q90", False)
            rows = [Forecast(household=hh[str(r["household_id"])], target_date=pd.to_datetime(r[dc]).date(),
                             horizon_days=hz, predicted_kwh=float(r[pc]), actual_kwh=num(r[ac]) if ac else None,
                             q10=num(r[q10]) if q10 else None, q90=num(r[q90]) if q90 else None)
                    for r in df.dropna(subset=[pc]).to_dict("records") if str(r["household_id"]) in hh]
            Forecast.objects.bulk_create(rows, batch_size=2000, update_conflicts=True,
                                         unique_fields=["household", "target_date", "horizon_days"],
                                         update_fields=["predicted_kwh", "actual_kwh", "q10", "q90"])
            self.stdout.write(f"{len(rows)} prévisions J+{hz}")

        if (proc / "profiles.csv").exists():
            df = read(proc / "profiles.csv")
            for r in df.to_dict("records"):
                if str(r["household_id"]) in hh:
                    HouseholdProfile.objects.update_or_create(household=hh[str(r["household_id"])], defaults={
                        "cluster": int(r["cluster"]), "profil": str(r["profil"]),
                        "evening_share": num(r["evening_share"]) if "evening_share" in df.columns else None,
                        "night_share": num(r["night_share"]) if "night_share" in df.columns else None})
            self.stdout.write(f"{len(df)} profils")

        if (proc / "anomalies_flagged.csv").exists():
            df = read(proc / "anomalies_flagged.csv")
            dc, tc, sc = pick(df, "date"), pick(df, "type"), pick(df, "severity")
            Alert.objects.all().delete()
            Alert.objects.bulk_create([Alert(household=hh.get(str(r["household_id"])), date=pd.to_datetime(r[dc]).date(),
                                             anomaly_type=str(r[tc]), severity=str(r[sc]))
                                       for r in df.to_dict("records")])
            self.stdout.write(f"{len(df)} anomalies")
        self.stdout.write(self.style.SUCCESS("Import terminé. Données synthétiques : à présenter comme telles."))
