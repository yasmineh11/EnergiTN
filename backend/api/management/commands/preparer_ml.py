"""Régénère data/ et models/ avec les scripts officiels de ml/ (graine 42), s'ils manquent.
    python manage.py preparer_ml            # ne fait rien si les modèles sont déjà là
    python manage.py preparer_ml --force    # relance toute la chaîne

Utile après un « git clone » : data/ et models/ ne sont pas sur GitHub (règle du guide),
seule la météo réelle data/raw/weather.csv est versionnée pour un résultat identique sans Internet."""
import subprocess
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.pipeline import STEPS, _args

CHAIN = ["generate", "prepare", "forecast_h1", "forecast_h7", "profiles", "anomalies"]


class Command(BaseCommand):
    help = "Régénère les données synthétiques et les modèles ML (graine 42) s'ils manquent"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="relancer même si les modèles existent")

    def handle(self, *a, force=False, **o):
        M = settings.ML_MODELS_DIR
        needed = [M / "forecast_h1.joblib", M / "forecast_h7.joblib",
                  settings.ML_DATA_DIR / "processed" / "daily.csv"]
        if not force and all(p.exists() for p in needed):
            self.stdout.write("✓ Données et modèles ML déjà présents")
            return
        self.stdout.write("Chaîne ML : génération des données et entraînement (5 à 15 min la première fois)")
        for s in CHAIN:
            label, script = STEPS[s]
            self.stdout.write(f"  ▶ {label}…")
            t = time.time()
            p = subprocess.run([sys.executable, "-I", script, *_args(s, {})], cwd=settings.ML_SCRIPTS_DIR,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p.returncode != 0:
                self.stderr.write((p.stdout or "")[-1500:] + (p.stderr or "")[-3000:])
                raise CommandError(f"Échec de l'étape « {label} » ({script})")
            self.stdout.write(f"    ok ({time.time() - t:.0f} s)")
        self.stdout.write(self.style.SUCCESS("✓ Données et modèles ML régénérés"))
