"""Exécution de la chaîne ML du guide depuis l'espace administrateur (UC14, UC15).
Chaque étape lance le script officiel (ml/*.py) avec le même interpréteur Python que Django,
dans un fil d'exécution séparé ; le journal est enregistré dans PipelineRun et affiché en direct."""
import io
import subprocess
import sys
import threading
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections
from django.utils import timezone

from .models import PipelineRun

STEPS = {
    "generate": ("Générer les données synthétiques", "generate_synthetic.py"),
    "prepare": ("Nettoyer et préparer (daily.csv)", "prepare.py"),
    "forecast_h1": ("Entraîner la prévision J+1", "train_forecast.py"),
    "forecast_h7": ("Entraîner la prévision J+7", "train_forecast.py"),
    "profiles": ("Calculer les profils (K-Means)", "profiles.py"),
    "anomalies": ("Détecter les anomalies", "anomalies.py"),
    "import": ("Importer les résultats dans Django", None),
    "inference": ("Calculer les prévisions (.joblib)", None),
}
ORDER = list(STEPS)
_LOCK = threading.Lock()


def _args(step, opts):
    data = settings.ML_DATA_DIR
    if step == "generate":
        a = ["--households", str(int(opts.get("households", 30))), "--seed", str(int(opts.get("seed", 42))),
             "--out", str(data / "synthetic")]
        weather = data / "raw" / "weather.csv"
        if weather.exists():
            a += ["--weather", str(weather)]
        return a
    # erreur météo simulée (°C) : 2 = réglage de l'équipe (évaluation réaliste, intervalle calibré en conséquence)
    werr = str(float(opts.get("weather_error", getattr(settings, "ML_WEATHER_ERROR", 2.0))))
    if step == "forecast_h1":
        return ["--horizon", "1", "--weather-error", werr]
    if step == "forecast_h7":
        return ["--horizon", "7", "--weather-error", werr]
    return []


def _run(run_id, steps, opts):
    close_old_connections()
    run = PipelineRun.objects.get(pk=run_id)

    def out(txt):
        run.log += txt
        run.save(update_fields=["log"])
    ok = True
    try:
        for s in steps:
            label, script = STEPS[s]
            out(f"\n▶ {label}\n")
            if script:
                p = subprocess.run([sys.executable, "-I", script, *_args(s, opts)], cwd=settings.ML_SCRIPTS_DIR,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
                lines = [l for l in (p.stdout + p.stderr).splitlines() if "Warning" not in l and "warnings.warn" not in l]
                out("\n".join(lines[-40:]) + "\n")
                if p.returncode != 0:
                    out(f"✗ Échec (code {p.returncode})\n")
                    ok = False
                    break
            elif s == "import":
                buf = io.StringIO()
                call_command("import_results", stdout=buf)
                out(buf.getvalue())
            elif s == "inference":
                from .ml import run_inference
                r = run_inference()
                out(f"{r['forecasts']} prévisions calculées pour {r['households'] - r['skipped']} foyers\n")
    except Exception as e:      # journalisé pour l'administrateur
        out(f"✗ Erreur : {e}\n")
        ok = False
    run.status = "ok" if ok else "error"
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at"])
    close_old_connections()


def start(user, steps, opts=None):
    steps = [s for s in ORDER if s in steps]
    with _LOCK:
        stale = timezone.now() - timedelta(hours=2)
        PipelineRun.objects.filter(status="running", started_at__lt=stale).update(status="error")
        if PipelineRun.objects.filter(status="running").exists():
            return None
        run = PipelineRun.objects.create(steps=steps, started_by=user, status="running")
    t = threading.Thread(target=_run, args=(run.pk, steps, opts or {}), daemon=True)
    t.start()
    return run
