from django.contrib import admin
from .models import (Alert, ChatMessage, DailyConsumption, Forecast, Holiday, Household, HouseholdProfile, ModelRun,
                     Outage, PipelineRun, TariffBand, UserProfile, Weather)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("household_id", "region", "persona", "ac_coef", "is_synthetic")
    list_filter = ("region", "persona", "is_synthetic")
    search_fields = ("household_id",)


@admin.register(DailyConsumption)
class DailyAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "kwh", "tmax", "source")
    list_filter = ("source",)
    search_fields = ("household__household_id",)
    date_hierarchy = "date"


@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ("household", "target_date", "kind", "horizon_days", "model_name", "predicted_kwh", "actual_kwh", "weather_source")
    list_filter = ("kind", "horizon_days", "model_name")
    search_fields = ("household__household_id",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("household", "date", "anomaly_type", "severity", "source", "is_resolved")
    list_filter = ("anomaly_type", "severity", "source", "is_resolved")


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ("name", "trained_at", "imported_at", "is_active")
    list_filter = ("name", "is_active")


admin.site.register(HouseholdProfile, list_display=("household", "cluster", "profil", "mean_day", "heat_sens"))
admin.site.register(UserProfile, list_display=("user", "role", "household"))
admin.site.register(Weather, list_display=("region", "date", "tmax", "source"), list_filter=("region", "source"))
admin.site.register(Holiday)
admin.site.register(Outage, list_display=("region", "start", "hours"))
admin.site.register(TariffBand, list_display=("order", "label", "max_kwh_year", "price_dt"))
admin.site.register(ChatMessage, list_display=("user", "role", "engine", "created_at"))
admin.site.register(PipelineRun, list_display=("started_at", "status", "started_by"))
