from rest_framework import serializers
from .models import Alert, Forecast, Household, HouseholdProfile


class HouseholdSerializer(serializers.ModelSerializer):
    region_id = serializers.CharField(read_only=True)

    class Meta:
        model = Household
        fields = ["id", "household_id", "region", "region_id", "persona", "ac_coef", "is_synthetic"]


class _WithHid(serializers.ModelSerializer):
    household_id = serializers.CharField(source="household.household_id", read_only=True)


class ForecastSerializer(_WithHid):
    class Meta:
        model = Forecast
        fields = ["id", "household_id", "target_date", "horizon_days", "kind", "model_name", "predicted_kwh",
                  "actual_kwh", "q10", "q90", "tmax_used", "weather_source"]


class HouseholdProfileSerializer(_WithHid):
    class Meta:
        model = HouseholdProfile
        fields = ["id", "household_id", "cluster", "profil", "mean_day", "evening_share", "night_share",
                  "summer_ratio", "load_factor", "heat_sens", "weekend_ratio"]


class AlertSerializer(_WithHid):
    class Meta:
        model = Alert
        fields = ["id", "household_id", "date", "anomaly_type", "severity", "kwh", "expected_kwh", "ratio",
                  "source", "description", "is_resolved"]


class ReadingSerializer(serializers.Serializer):
    date = serializers.DateField()
    kwh = serializers.FloatField(min_value=0, max_value=200)
