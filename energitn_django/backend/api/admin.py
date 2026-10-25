from django.contrib import admin
from .models import Household, DailyConsumption, Forecast, HouseholdProfile, Alert, UserProfile

admin.site.register(Household, list_display=("household_id", "region", "persona"))
admin.site.register(Forecast, list_display=("household", "target_date", "horizon_days", "predicted_kwh"))
admin.site.register(HouseholdProfile, list_display=("household", "cluster", "profil"))
admin.site.register(Alert, list_display=("household", "date", "anomaly_type", "severity", "is_resolved"))
admin.site.register(UserProfile, list_display=("user", "role", "household"))
admin.site.register(DailyConsumption, list_display=("household", "date", "kwh"))
