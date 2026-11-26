"""Tests des fonctions critiques (NF10) : import ML, inférence .joblib, accès par rôle, détection, assistant, admin.
    python manage.py test api"""
import json
import warnings
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from api import billing, ml
from api.facts import household_facts, rules_answer
from api.management.commands.bootstrap import DEMO_PASSWORD, create_demo_accounts
from api.models import Alert, DailyConsumption, Forecast, Holiday, Household, ModelRun, TariffBand

warnings.filterwarnings("ignore")


class EnergiTNTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_results", stdout=StringIO())
        ml.run_inference()
        create_demo_accounts()

    def login(self, who):
        self.assertTrue(self.client.login(username=who, password=DEMO_PASSWORD))

    # ---------------------------------------------------------------- liaison ML
    def test_import_and_modelrun(self):
        self.assertEqual(Household.objects.count(), 30)
        self.assertTrue(Forecast.objects.filter(kind="backtest", actual_kwh__isnull=False).exists())
        self.assertEqual(set(ModelRun.objects.filter(is_active=True).values_list("name", flat=True)),
                         {"forecast_h1", "forecast_h7", "profiles", "anomalies"})

    def test_inference_matches_team_inference(self):
        """Django donne la même prévision J+1 que ml/inference.py (code de l'équipe), à météo identique.
        (On ne compare plus aux prédictions de train_forecast.py : elles sont calculées avec une erreur
        météo simulée de ±2 °C, alors que Django utilise la météo réelle.)"""
        import sys
        import pandas as pd
        from django.conf import settings
        sys.path.insert(0, str(settings.ML_SCRIPTS_DIR))
        import inference
        hh = list(Household.objects.order_by("household_id")[:5])
        rows = [{"household_id": h.household_id, "date": pd.Timestamp(d), "kwh_day": k, "region": h.region,
                 "persona": h.persona, "ac_coef": h.ac_coef}
                for h in hh for d, k in DailyConsumption.objects.filter(household=h).values_list("date", "kwh")]
        fc = {f.household.household_id: f for f in Forecast.objects.filter(kind="future", horizon_days=1, household__in=hh)}
        wx = pd.DataFrame([{"date": pd.Timestamp(f.target_date), "region": f.household.region, "tmax": f.tmax_used}
                           for f in fc.values()]).drop_duplicates(["date", "region"])
        hol = {pd.Timestamp(d) for d in Holiday.objects.values_list("date", flat=True)}
        out = inference.forecast_next_days(pd.DataFrame(rows), wx, hol, ml.load_model(1), days=1)
        self.assertEqual(len(out), 5)
        for r in out.itertuples():
            f = fc[r.household_id]
            self.assertAlmostEqual(r.predicted, f.predicted_kwh, delta=0.01)
            self.assertAlmostEqual(r.low, f.q10, delta=0.01)
            self.assertAlmostEqual(r.high, f.q90, delta=0.01)
            self.assertLessEqual(f.q10, f.predicted_kwh)
            self.assertLessEqual(f.predicted_kwh, f.q90)

    def test_future_forecasts(self):
        h = Household.objects.first()
        fc = list(h.forecasts.filter(kind="future").order_by("target_date"))
        self.assertEqual(len(fc), 7)
        self.assertEqual(fc[0].model_name, "forecast_h1")
        self.assertEqual(fc[1].model_name, "forecast_h7")
        last = h.daily.order_by("-date").first().date
        self.assertEqual(fc[0].target_date, last + timedelta(days=1))

    def test_live_anomaly_and_reforecast(self):
        h = Household.objects.get(household_id="H001")
        last = h.daily.order_by("-date").first().date
        res = ml.save_readings(h, [(last + timedelta(days=1), 200.0)])
        self.assertEqual(len(res["alerts"]), 1)
        self.assertEqual(res["alerts"][0].source, "live")
        self.assertEqual(h.forecasts.filter(kind="future").first().target_date, last + timedelta(days=2))

    def test_insufficient_history(self):
        h = Household.objects.create(household_id="U999", region="Tunis", persona="couple_actif")
        self.assertEqual(ml.forecast_household(h), 0)

    # ---------------------------------------------------------------- facture et assistant
    def test_billing_whole_consumption_rule(self):
        e = billing.estimate(150, 30)                 # 1 825 kWh/an -> première tranche
        self.assertEqual(e["band"], 0)
        self.assertAlmostEqual(e["total"], 150 * 0.181, places=2)
        self.assertIn("next_band", e)

    def test_assistant_rules_grounded(self):
        f = household_facts(Household.objects.get(household_id="H004"))
        a = rules_answer("Pourquoi ma facture augmente ?", f, "fr")
        self.assertIn(str(int(round(f["month"]["bill"]["total"]))), a.replace(" ", ""))
        self.assertIn("Je réponds", rules_answer("Quel temps fait-il à Paris ?", f, "fr"))
        self.assertTrue(any("؀" <= c <= "ۿ" for c in rules_answer("اشرح تنبيهي", f, "ar")))

    # ---------------------------------------------------------------- accès et parcours
    def test_role_access(self):
        self.assertEqual(self.client.get("/foyer/").status_code, 302)
        self.assertEqual(self.client.get("/api/forecasts/").status_code, 403)
        self.login("foyer@demo.tn")
        self.assertEqual(self.client.get("/foyer/").status_code, 200)
        self.assertEqual(self.client.get("/analyste/").status_code, 302)
        self.assertEqual(self.client.get("/api/operator/overview/").status_code, 403)
        ids = {f["household_id"] for f in self.client.get("/api/forecasts/").json()["results"]}
        self.assertEqual(len(ids), 1)
        self.login("analyste@demo.tn")
        for u in ("/analyste/", "/analyste/profils/", "/analyste/anomalies/"):
            self.assertEqual(self.client.get(u).status_code, 200)
        self.assertEqual(self.client.get("/gestion/").status_code, 302)
        self.assertEqual(len(self.client.get("/api/operator/overview/").json()["regions"]), 6)

    def test_all_foyer_pages_bilingual(self):
        self.login("foyer@demo.tn")
        for lang in ("fr", "ar"):
            self.client.cookies["lang"] = lang
            for u in ("/foyer/", "/foyer/releves/", "/foyer/facture/", "/foyer/profil/", "/foyer/assistant/", "/foyer/rapport/"):
                r = self.client.get(u)
                self.assertEqual(r.status_code, 200, u)
                self.assertIn(f'dir="{"rtl" if lang == "ar" else "ltr"}"', r.content.decode())

    def test_register_own_household_and_readings(self):
        r = self.client.post("/register/", {"name": "Test", "username": "t@x.tn", "password": "Kairouan#2026", "password2": "Kairouan#2026",
                                            "mode": "own", "region": "sfx", "persona": "couple_actif", "ac": "1.0", "consent": "on"})
        self.assertRedirects(r, "/foyer/")
        h = get_user_model().objects.get(username="t@x.tn").profile.household
        self.assertFalse(h.is_synthetic)
        csv = "date,kwh\n" + "\n".join(f"2026-09-{d:02d},{10 + d % 3}" for d in range(1, 21))
        r = self.client.post("/foyer/releves/", {"action": "file", "file": SimpleUploadedFile("r.csv", csv.encode())})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(DailyConsumption.objects.filter(household=h).count(), 20)
        self.assertEqual(Forecast.objects.filter(household=h, kind="future").count(), 7)

    def test_register_weak_password_rejected(self):
        r = self.client.post("/register/", {"name": "A", "username": "a@x.tn", "password": "12345678", "password2": "12345678",
                                            "mode": "demo", "region": "tun", "consent": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="a@x.tn").exists())

    def test_assistant_and_resolve(self):
        self.login("foyer@demo.tn")
        r = self.client.post("/foyer/assistant/ask/", {"q": "Explique mon alerte"}, content_type="application/json")
        self.assertEqual(r.json()["engine"], "regles")
        a = Alert.objects.filter(household__household_id=get_user_model().objects.get(username="foyer@demo.tn").profile.household.household_id).first()
        r = self.client.post("/foyer/alertes/resoudre/", {"id": a.id}, content_type="application/json")
        self.assertTrue(r.json()["ok"])
        other = Alert.objects.exclude(household=a.household).first()
        r = self.client.post("/foyer/alertes/resoudre/", {"id": other.id}, content_type="application/json")
        self.assertEqual(r.status_code, 404)          # NF08 : pas d'accès aux alertes d'un autre foyer

    def test_admin_actions(self):
        self.login("admin@demo.tn")
        for u in ("/gestion/", "/gestion/donnees/", "/gestion/modeles/", "/gestion/referentiel/"):
            self.assertEqual(self.client.get(u).status_code, 200)
        r = self.client.post("/gestion/user/", {"email": "n@x.tn", "password": "Kairouan#2026", "role": "analyste"}, content_type="application/json")
        self.assertTrue(r.json()["ok"])
        me = get_user_model().objects.get(username="admin@demo.tn")
        r = self.client.post("/gestion/user/", {"id": me.id, "role": "foyer", "active": True}, content_type="application/json")
        self.assertEqual(r.json()["error"], "e_self")
        r = self.client.post("/gestion/tarifs/", {"bands": [{"label": "A", "max": 3000, "price": "0.2"}, {"label": "B", "max": "", "price": "0.4"}]},
                             content_type="application/json")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(TariffBand.objects.count(), 2)
        r = self.client.post("/gestion/profils/", {"names": {"0": "Soirées chargées"}}, content_type="application/json")
        self.assertTrue(r.json()["ok"])
        wx = "date,region,tmax\n" + "\n".join(f"2026-10-0{d},Gabès,36" for d in range(1, 8))
        r = self.client.post("/gestion/meteo/", {"file": SimpleUploadedFile("w.csv", wx.encode())})
        self.assertTrue(r.json()["ok"])
        self.assertEqual(Forecast.objects.filter(kind="future", household__region="Gabes", target_date__day=2).first().weather_source, "prevision")

    def test_non_admin_blocked(self):
        self.login("analyste@demo.tn")
        self.assertEqual(self.client.post("/gestion/pipeline/", {"steps": ["import"]}, content_type="application/json").status_code, 403)

    # ---------------------------------------------------------------- v3 : liaison ML à la demande
    def test_ml_predict_endpoint(self):
        """Option B du guide : POST /api/ml/predict/ recharge les .joblib et renvoie J+1..J+7."""
        self.login("analyste@demo.tn")
        r = self.client.post("/api/ml/predict/", {"household_id": "H001"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        fc = r.json()["forecasts"]
        self.assertEqual(len(fc), 7)
        self.assertTrue(all(f["q10"] <= f["predicted_kwh"] <= f["q90"] for f in fc))
        self.assertEqual(self.client.post("/api/ml/predict/", {"household_id": "XXX"}, content_type="application/json").status_code, 404)

    def test_foyer_cannot_predict_other_household(self):
        """Un foyer recalcule uniquement son propre foyer, même s'il en demande un autre."""
        self.login("foyer@demo.tn")
        r = self.client.post("/api/ml/predict/", {"household_id": "H001"}, content_type="application/json")
        self.assertEqual(r.json()["household_id"], "H004")

    def test_heat_scenario_increases_consumption(self):
        """Jumeau numérique : +5 °C fait monter la consommation prévue par les modèles."""
        self.login("foyer@demo.tn")
        r = self.client.get("/api/foyer/scenario/?delta=5").json()
        self.assertEqual(len(r["days"]), 7)
        self.assertGreater(r["scenario_kwh"], r["base_kwh"])
        self.assertGreaterEqual(r["bill_scenario"], r["bill_base"])
        z = self.client.get("/api/foyer/scenario/?delta=0").json()
        self.assertAlmostEqual(z["scenario_kwh"], z["base_kwh"], places=1)

    def test_ml_health_and_drift(self):
        self.login("admin@demo.tn")
        r = self.client.get("/api/ml/health/").json()
        self.assertEqual(r["score"], r["total"])
        self.assertIn(r["drift"]["status"], ("ok", "watch", "drift"))
        self.login("foyer@demo.tn")
        self.assertEqual(self.client.get("/api/ml/health/").status_code, 403)

    def test_open_alert_count_not_capped(self):
        h = Household.objects.get(household_id="H004")
        self.assertEqual(household_facts(h)["alerts_open"], Alert.objects.filter(household=h, is_resolved=False).count())
