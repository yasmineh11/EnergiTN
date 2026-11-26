from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("households", views.HouseholdViewSet, basename="household")
router.register("forecasts", views.ForecastViewSet, basename="forecast")
router.register("profiles", views.ProfileViewSet, basename="profile")
router.register("anomalies", views.AlertViewSet, basename="anomaly")

urlpatterns = [
    path("", views.accueil_api, name="api-home"),
    path("foyer/dashboard/", views.foyer_dashboard_api),
    path("foyer/facts/", views.foyer_facts_api),
    path("foyer/readings/", views.foyer_readings_api),
    path("operator/overview/", views.operator_overview),
    path("operator/profiles/", views.operator_profiles),
    path("operator/anomalies/", views.operator_anomalies),
    path("models/", views.models_api),
    path("ml/health/", views.ml_health_api),
    path("ml/predict/", views.ml_predict_api),
    path("foyer/scenario/", views.foyer_scenario_api),
    path("", include(router.urls)),
]
