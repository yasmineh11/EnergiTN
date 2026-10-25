"""Données de démonstration SYNTHÉTIQUES (30 foyers, 6 régions) + 3 comptes de test.
Utile pour lancer le projet avant d'avoir exécuté la chaîne ML.
    python manage.py seed_demo [--reset]"""
import math, random
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from api.models import Household, DailyConsumption, Forecast, HouseholdProfile, Alert, UserProfile
from api.regions import REGIONS

TREF = {"tun": 20, "biz": 19, "sou": 20, "sfx": 21, "gab": 22, "toz": 24}
PERSONAS = [("soir", "Pic du soir"), ("clim", "Gros climatiseur"), ("econome", "Foyer économe"), ("jour", "Présence en journée")]
END = date(2026, 10, 21)


def tmax(rid, d, rnd):
    doy = d.timetuple().tm_yday
    return TREF[rid] + 8 * math.cos((doy - 200) / 365 * 2 * math.pi) + 5 + rnd.uniform(-2, 2)


def kwh(base, ac, t, d):
    return base + max(0, t - 24) * ac + (1.6 if d.weekday() >= 5 else 0)


class Command(BaseCommand):
    help = "Génère des données synthétiques de démonstration"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")

    def handle(self, *a, **o):
        if Household.objects.exists():
            if not o["reset"]:
                return self.stdout.write("Des données existent déjà (utilisez --reset pour tout régénérer).")
            for m in (Alert, Forecast, DailyConsumption, HouseholdProfile, Household):
                m.objects.all().delete()
        rnd = random.Random(42)
        daily, fcs = [], []
        for i in range(30):
            reg = REGIONS[(i + 3) % 6]            # H001 → Sfax
            pk, pname = PERSONAS[i % 4]
            h = Household.objects.create(household_id=f"H{i+1:03d}", region=reg["fr"], persona=pk)
            base = rnd.uniform(6, 9) * (0.85 if pk == "econome" else 1)
            ac = rnd.uniform(.3, .8) * (1.4 if pk == "clim" else 1)
            HouseholdProfile.objects.create(
                household=h, cluster=i % 4, profil=pname,
                evening_share=rnd.randint(46, 58) if pk == "soir" else rnd.randint(28, 42),
                night_share=rnd.randint(14, 24), summer_ratio=rnd.randint(45, 90))
            anom = {END - timedelta(days=12)} if i % 5 == 0 else set()
            d = date(2026, 7, 1)
            while d <= END:
                t = tmax(reg["id"], d, rnd)
                k = kwh(base, ac, t, d) + rnd.uniform(-.8, .8)
                if d in anom:
                    k *= 1.7
                    Alert.objects.create(household=h, date=d, anomaly_type="Écart avec la prévision",
                                         severity="medium", description="Consommation 70 % au-dessus de la prévision.")
                daily.append(DailyConsumption(household=h, date=d, kwh=round(k, 2), tmax=round(t, 1)))
                if d >= END - timedelta(days=59):   # prévisions rétrospectives : prévu vs réel (qualité des modèles)
                    p0 = kwh(base, ac, t, d)
                    fcs.append(Forecast(household=h, target_date=d, horizon_days=1, predicted_kwh=round(p0 + rnd.uniform(-.4, .4), 2),
                                        actual_kwh=round(k, 2), q10=round(p0 * .9, 2), q90=round(p0 * 1.1, 2)))
                d += timedelta(days=1)
            for j in range(1, 8):                 # 7 jours de prévision, avec une vague de chaleur en fin de période
                d = END + timedelta(days=j)
                t = tmax(reg["id"], d, rnd) + (8 if j >= 3 else 0)
                p = kwh(base, ac, t, d)
                fcs.append(Forecast(household=h, target_date=d, horizon_days=1,
                                    predicted_kwh=round(p, 2), q10=round(p * .9, 2), q90=round(p * 1.1, 2)))
        DailyConsumption.objects.bulk_create(daily)
        Forecast.objects.bulk_create(fcs)
        U = get_user_model()
        for email, role, hh, su in (("foyer@demo.tn", "foyer", "H001", False),
                                    ("analyste@demo.tn", "analyste", None, False),
                                    ("admin@demo.tn", "admin", None, True)):
            u, _ = U.objects.get_or_create(username=email, defaults={"email": email, "is_staff": su, "is_superuser": su})
            u.set_password("demo1234"); u.save()
            UserProfile.objects.update_or_create(user=u, defaults={
                "role": role, "household": Household.objects.filter(household_id=hh).first() if hh else None})
        self.stdout.write(self.style.SUCCESS("Démo prête : foyer@demo.tn, analyste@demo.tn, admin@demo.tn (mot de passe : demo1234)"))
