from django.urls import path

from . import api

urlpatterns = [
    path("households/<str:code>/consumption/", api.consumption),
    path("households/<str:code>/forecast/", api.forecast),
    path("households/<str:code>/profile/", api.profile),
    path("households/<str:code>/alerts/", api.alerts),
    path("households/<str:code>/bill/", api.bill),
    path("households/<str:code>/assistant/", api.assistant),
]
# Dans config/urls.py : path("api/energy/", include("energy.urls"))   (évite tout conflit avec votre app "api")
