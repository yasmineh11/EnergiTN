from rest_framework import serializers
from .models import Household, Forecast, HouseholdProfile, Alert


class HouseholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Household
        fields = "__all__"


class _WithHid(serializers.ModelSerializer):
    household_id = serializers.CharField(source="household.household_id", read_only=True)


class ForecastSerializer(_WithHid):
    class Meta:
        model = Forecast
        fields = ["id", "household_id", "target_date", "horizon_days", "predicted_kwh", "actual_kwh", "q10", "q90"]


class HouseholdProfileSerializer(_WithHid):
    class Meta:
        model = HouseholdProfile
        fields = ["id", "household_id", "cluster", "profil"]


class AlertSerializer(_WithHid):
    class Meta:
        model = Alert
        fields = ["id", "household_id", "date", "anomaly_type", "severity", "description", "is_resolved"]
