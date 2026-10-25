"""Tâches Celery : l'interface ne calcule rien de lourd, tout se fait ici en arrière-plan."""
import subprocess
import sys
from datetime import date
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.management import call_command

ML_STEPS = [["prepare.py"], ["train_forecast.py", "--horizon", "1"], ["train_forecast.py", "--horizon", "7"],
            ["profiles.py"], ["anomalies.py"]]


@shared_task
def weekly_retrain():
    """Réentraîne les modèles (scripts du dossier ml/) puis recharge les résultats en base."""
    ml_dir = Path(settings.ML_ROOT) / "ml"
    for step in ML_STEPS:
        subprocess.run([sys.executable, *step], cwd=ml_dir, check=True)
    call_command("import_ml_results")


@shared_task
def nightly_forecast(as_of=None):
    """Prévoit les 7 prochains jours à partir du dernier jour connu (par défaut : aujourd'hui)."""
    call_command("forecast_future", "--as-of", as_of or date.today().isoformat(), "--days", "7")
