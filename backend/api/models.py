"""Modèles de données ÉnergiTN.
Tables alimentées par la chaîne ML (guide des fichiers) : Household, DailyConsumption, Forecast,
HouseholdProfile, Alert, Weather, Holiday, Outage, ModelRun.
Tables applicatives : UserProfile, ChatMessage, TariffBand, PipelineRun."""
from django.conf import settings
from django.db import models
from .regions import region_of

PERSONAS = {
    "etudiant_appartement": ("Étudiant en appartement", "طالب في شقة"),
    "famille_5_villa": ("Famille de 5 en villa", "عائلة من 5 أفراد في فيلا"),
    "couple_actif": ("Couple actif", "زوجان عاملان"),
    "retraite_a_la_maison": ("Retraité à la maison", "متقاعد في المنزل"),
}


class Household(models.Model):
    """"Cette classe représente les foyers tunisiens qui utilisent l'électricité."""
    household_id = models.CharField(max_length=80, unique=True)
    region = models.CharField(max_length=80, help_text="Nom de région utilisé par la chaîne ML (ex. Gabes)")
    persona = models.CharField(max_length=80, blank=True)
    ac_coef = models.FloatField(default=1.0, help_text="Coefficient de climatisation (feature du modèle)")
    is_synthetic = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["household_id"]

    @property
    def region_info(self):
        return region_of(self.region)

    @property
    def region_id(self):
        r = region_of(self.region)
        return r["id"] if r else None

    def __str__(self):
        return self.household_id


class DailyConsumption(models.Model):
    """Enregistrer la consommation électrique de chaque foyer, chaque jour."""
    SOURCES = [("ml", "Chaîne ML (daily.csv)"), ("saisie", "Saisie manuelle"), ("import", "Import fichier")]
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="daily")
    date = models.DateField()
    kwh = models.FloatField()
    tmax = models.FloatField(null=True, blank=True)
    outage_h = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=10, choices=SOURCES, default="ml")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["household", "date"], name="unique_daily")]
        indexes = [models.Index(fields=["date"]), models.Index(fields=["household", "date"])]
        ordering = ["household", "date"]


class Forecast(models.Model):
    """kind=backtest : prévu contre réel issu de forecast_h*_predictions.csv (validation/test).
    kind=future   : prévision calculée par Django en chargeant les .joblib (inférence)."""
    KINDS = [("backtest", "Évaluation (CSV)"), ("future", "Prévision (inférence .joblib)")]
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="forecasts")
    target_date = models.DateField()
    horizon_days = models.PositiveSmallIntegerField(default=1)
    kind = models.CharField(max_length=10, choices=KINDS, default="backtest")
    model_name = models.CharField(max_length=40, blank=True)
    predicted_kwh = models.FloatField()
    actual_kwh = models.FloatField(null=True, blank=True)
    q10 = models.FloatField(null=True, blank=True)
    q90 = models.FloatField(null=True, blank=True)
    tmax_used = models.FloatField(null=True, blank=True)
    weather_source = models.CharField(max_length=20, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["household", "target_date", "horizon_days", "kind"], name="unique_household_forecast")]
        indexes = [models.Index(fields=["kind", "target_date"])]


class HouseholdProfile(models.Model):
    #Enregistrer le comportement énergétique d'un foyer.#
    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="profile")
    cluster = models.IntegerField()
    profil = models.CharField(max_length=160)
    mean_day = models.FloatField(null=True, blank=True)
    evening_share = models.FloatField(null=True, blank=True, help_text="% de la conso entre 18 h et 23 h")
    night_share = models.FloatField(null=True, blank=True, help_text="% de la conso entre 0 h et 5 h")
    summer_ratio = models.FloatField(null=True, blank=True)
    load_factor = models.FloatField(null=True, blank=True)
    heat_sens = models.FloatField(null=True, blank=True, help_text="kWh/jour supplémentaires par degré au-dessus de 24 °C")
    weekend_ratio = models.FloatField(null=True, blank=True)
    hourly = models.JSONField(default=dict, blank=True, help_text="Journée type : {all, summer, winter} -> 24 valeurs kWh")


class Alert(models.Model):
    #Enregistrer les anomalies détectées dans la consommation électrique#
    TYPES = [("surconsommation", "Surconsommation"), ("consommation_nocturne", "Consommation nocturne"),
             ("ecart_prevision", "Écart avec la prévision")]
    SEVERITIES = [("haute", "Haute"), ("moyenne", "Moyenne"), ("basse", "Basse")]
    SOURCES = [("ml", "anomalies.py"), ("live", "Détection à la saisie")]
    household = models.ForeignKey(Household, on_delete=models.CASCADE, null=True, blank=True, related_name="alerts")
    date = models.DateField()
    anomaly_type = models.CharField(max_length=40, choices=TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITIES, default="moyenne")
    kwh = models.FloatField(null=True, blank=True)
    expected_kwh = models.FloatField(null=True, blank=True)
    ratio = models.FloatField(null=True, blank=True)
    night_ratio = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default="ml")
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]#-date : ordre décroissant#
        constraints = [models.UniqueConstraint(fields=["household", "date", "anomaly_type"], name="unique_alert")]


class Weather(models.Model):
    region = models.CharField(max_length=80)
    date = models.DateField()
    tmax = models.FloatField()
    tmean = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=20, default="observee")   # observee | prevision

    class Meta:
        constraints = [models.UniqueConstraint(fields=["region", "date"], name="unique_weather")]


class Holiday(models.Model):
    date = models.DateField(unique=True)


class Outage(models.Model):
    region = models.CharField(max_length=80)
    start = models.DateTimeField()
    hours = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-start"]


class ModelRun(models.Model):
    """Trace des modèles entraînés (scores des *_metrics.json), comme demandé par le guide."""
    name = models.CharField(max_length=40)          # forecast_h1, forecast_h7, profiles, anomalies
    metrics = models.JSONField(default=dict)
    trained_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    artifact = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-imported_at"]


class TariffBand(models.Model):
    """Barème d'électricité (données de référence modifiables par l'administrateur).
    La tranche est choisie selon la consommation annualisée ; son prix s'applique à toute la consommation."""
    label = models.CharField(max_length=80)
    max_kwh_year = models.PositiveIntegerField(null=True, blank=True, help_text="Vide = sans plafond")
    price_dt = models.DecimalField(max_digits=6, decimal_places=3, help_text="Prix en DT par kWh")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class UserProfile(models.Model):
    ROLES = [("foyer", "Foyer"), ("analyste", "Analyste énergétique"), ("admin", "Administrateur")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLES, default="foyer")
    household = models.ForeignKey(Household, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.user} ({self.role})"


class ChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat")
    role = models.CharField(max_length=10)          # user | assistant
    content = models.TextField()
    lang = models.CharField(max_length=2, default="fr")
    engine = models.CharField(max_length=20, blank=True)   # llm | regles
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PipelineRun(models.Model):
    """Exécution de la chaîne ML depuis l'espace administrateur."""
    status = models.CharField(max_length=10, default="running")   # running | ok | error
    steps = models.JSONField(default=list)
    log = models.TextField(blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
