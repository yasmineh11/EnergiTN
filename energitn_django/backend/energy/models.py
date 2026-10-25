from django.conf import settings
from django.db import models


class Region(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Household(models.Model):
    code = models.CharField(max_length=10, unique=True)               # H001 (identifiant pseudonymisé)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="households")
    persona = models.CharField(max_length=40, blank=True)
    ac_coef = models.FloatField(default=1.0)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="households")
    is_synthetic = models.BooleanField(default=True)                  # exigence de transparence du cahier des charges

    def __str__(self):
        return self.code


class DailyConsumption(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="daily")
    date = models.DateField(db_index=True)
    kwh = models.FloatField(null=True, blank=True)                    # consommation du jour (estimée si coupure)
    outage_hours = models.PositiveSmallIntegerField(default=0)
    tmax = models.FloatField(null=True, blank=True)
    is_holiday = models.BooleanField(default=False)

    class Meta:
        unique_together = ("household", "date")
        ordering = ["date"]


class ModelRun(models.Model):
    """Une ligne par modèle entraîné : l'administrateur suit la qualité des prévisions (US15)."""
    name = models.CharField(max_length=40)                            # forecast_h1, forecast_h7, anomaly
    horizon = models.PositiveSmallIntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Forecast(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="forecasts")
    date = models.DateField(db_index=True)                            # jour prévu
    horizon = models.PositiveSmallIntegerField()                      # prévu X jours à l'avance
    predicted = models.FloatField()
    low = models.FloatField()
    high = models.FloatField()                                        # intervalle = indicateur de confiance
    actual = models.FloatField(null=True, blank=True)                 # rempli quand on connaît le réel
    model_run = models.ForeignKey(ModelRun, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("household", "date", "horizon")
        ordering = ["date"]


class Profile(models.Model):
    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="profile")
    cluster = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=120)


class Alert(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "Faible"
        MEDIUM = "medium", "Moyenne"
        HIGH = "high", "Haute"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="alerts")
    date = models.DateField()
    kind = models.CharField(max_length=30)                            # overconsumption, night_load, outage...
    severity = models.CharField(max_length=10, choices=Severity.choices)
    ratio = models.FloatField(null=True, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("household", "date", "kind")
        ordering = ["-date"]
