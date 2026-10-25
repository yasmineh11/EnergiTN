from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("households", views.HouseholdViewSet, basename="household")
router.register("forecasts", views.ForecastViewSet, basename="forecast")
router.register("profiles", views.ProfileViewSet, basename="profile")
router.register("anomalies", views.AlertViewSet, basename="anomaly")

urlpatterns = [
    path("", views.accueil_api, name="api-home"),
    path("foyer/dashboard/", views.foyer_dashboard),
    path("operator/overview/", views.operator_overview),
    path("", include(router.urls)),
]
