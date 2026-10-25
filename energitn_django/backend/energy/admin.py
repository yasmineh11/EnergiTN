"""L'admin Django sert d'espace d'administration (comptes, données, qualité des modèles) : plusieurs jours gagnés."""
from django.contrib import admin

from .models import Alert, DailyConsumption, Forecast, Household, ModelRun, Profile, Region

admin.site.register(Region)
admin.site.register(Profile)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("code", "region", "persona", "owner", "is_synthetic")
    list_filter = ("region", "persona")


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ("name", "horizon", "created_at")          # le champ "metrics" (JSON) = qualité des prévisions (US15)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "kind", "severity", "is_read")
    list_filter = ("severity", "kind")


@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "horizon", "predicted", "low", "high", "actual")
    list_filter = ("horizon",)


@admin.register(DailyConsumption)
class DailyAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "kwh", "outage_hours", "tmax")
    list_filter = ("household",)
