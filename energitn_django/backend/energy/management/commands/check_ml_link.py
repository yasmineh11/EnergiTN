"""
Vérifie que Django "voit" bien la partie ML (chemins, fichiers, modèle). À lancer en premier :

    python manage.py check_ml_link
"""
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Diagnostic de la liaison Django <-> ML."

    def handle(self, *args, **opts):
        root = Path(settings.ML_ROOT)
        self.stdout.write(f"ML_ROOT = {root}")
        checks = {
            "dossier ml/": root / "ml",
            "ml/inference.py": root / "ml" / "inference.py",
            "data/synthetic/households.csv": root / "data" / "synthetic" / "households.csv",
            "data/synthetic/weather_used.csv": root / "data" / "synthetic" / "weather_used.csv",
            "data/synthetic/holidays_used.csv": root / "data" / "synthetic" / "holidays_used.csv",
            "data/processed/daily.csv": root / "data" / "processed" / "daily.csv",
            "data/processed/forecast_h1_predictions.csv": root / "data" / "processed" / "forecast_h1_predictions.csv",
            "data/processed/profiles.csv": root / "data" / "processed" / "profiles.csv",
            "data/processed/anomalies_flagged.csv": root / "data" / "processed" / "anomalies_flagged.csv",
            "models/forecast_h1.joblib": root / "models" / "forecast_h1.joblib",
            "models/forecast_h7.joblib": root / "models" / "forecast_h7.joblib",
        }
        bad = 0
        for label, p in checks.items():
            ok = p.exists()
            bad += not ok
            self.stdout.write((self.style.SUCCESS("  OK       ") if ok else self.style.ERROR("  MANQUANT ")) + label)
        if not (root / "ml").exists():
            self.stdout.write(self.style.ERROR("\nLe dossier ml/ est introuvable : corrigez ML_ROOT dans settings.py "
                                               "(il doit pointer vers le dossier energitn qui contient ml/, data/ et models/)."))
            return
        try:
            import joblib
            import sklearn
            sys.path.insert(0, str(root / "ml"))
            from inference import forecast_next_days  # noqa: F401
            if checks["models/forecast_h1.joblib"].exists():
                b = joblib.load(checks["models/forecast_h1.joblib"])
                self.stdout.write(self.style.SUCCESS(
                    f"\nModèle chargé (scikit-learn {sklearn.__version__}) : {len(b['features'])} variables, "
                    f"hybride={b.get('hybrid')}, marge d'intervalle={b.get('interval_margin'):.3f}"))
        except Exception as e:                                           # version de scikit-learn différente, module absent...
            self.stdout.write(self.style.ERROR(f"\nChargement du modèle impossible : {e!r}\n"
                                               "Cause fréquente : Django n'utilise pas le même environnement Python que le ML."))
        if bad:
            self.stdout.write(self.style.WARNING(f"\n{bad} fichier(s) manquant(s) : relancez la chaîne ML (voir le guide)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nTout est prêt : lancez import_ml_results."))
