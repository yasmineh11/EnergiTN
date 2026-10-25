from django.conf import settings
from django.db import models
from .regions import region_of


class Household(models.Model):
    household_id = models.CharField(max_length=80, unique=True)
    region = models.CharField(max_length=80)
    persona = models.CharField(max_length=80, blank=True)

    @property
    def region_id(self):
        r = region_of(self.region)
        return r["id"] if r else None

    def __str__(self):
        return self.household_id


class DailyConsumption(models.Model):
    """Une ligne par foyer et par jour (daily.csv)."""
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="daily")
    date = models.DateField()
    kwh = models.FloatField()
    tmax = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["household", "date"], name="unique_daily")]
        indexes = [models.Index(fields=["date"])]


class Forecast(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="forecasts")
    target_date = models.DateField()
    horizon_days = models.PositiveSmallIntegerField(default=1)
    predicted_kwh = models.FloatField()
    actual_kwh = models.FloatField(null=True, blank=True)
    q10 = models.FloatField(null=True, blank=True)
    q90 = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["household", "target_date", "horizon_days"], name="unique_household_forecast")]


class HouseholdProfile(models.Model):
    household = models.OneToOneField(Household, on_delete=models.CASCADE, related_name="profile")
    cluster = models.IntegerField()
    profil = models.CharField(max_length=120)
    # optionnels : renseignés si profiles.csv contient ces colonnes (en %)
    evening_share = models.FloatField(null=True, blank=True)
    night_share = models.FloatField(null=True, blank=True)
    summer_ratio = models.FloatField(null=True, blank=True)


class Alert(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    anomaly_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]


class UserProfile(models.Model):
    ROLES = [("foyer", "Foyer"), ("analyste", "Analyste énergétique"), ("admin", "Administrateur")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLES, default="foyer")
    household = models.ForeignKey(Household, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.user} ({self.role})"
