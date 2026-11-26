from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("langue/<str:code>/", views.set_lang, name="lang"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    # espace foyer
    path("foyer/", views.foyer_page, name="foyer"),
    path("foyer/releves/", views.foyer_releves, name="releves"),
    path("foyer/releves/modele.csv", views.readings_template),
    path("foyer/facture/", views.foyer_facture, name="facture"),
    path("foyer/profil/", views.foyer_profil, name="profil"),
    path("foyer/alertes/resoudre/", views.resolve_alert),
    path("foyer/assistant/", views.foyer_assistant, name="assistant"),
    path("foyer/assistant/ask/", views.assistant_ask),
    path("foyer/assistant/effacer/", views.assistant_clear),
    path("foyer/rapport/", views.foyer_rapport, name="rapport"),
    # espace analyste
    path("analyste/", views.analyste_previsions, name="analyste"),
    path("analyste/profils/", views.analyste_profils, name="analyste_profils"),
    path("analyste/anomalies/", views.analyste_anomalies, name="analyste_anomalies"),
    path("operateur/", RedirectView.as_view(url="/analyste/", permanent=True)),
    # administration
    path("gestion/", views.gestion_page, name="gestion"),
    path("gestion/donnees/", views.gestion_donnees, name="gestion_donnees"),
    path("gestion/modeles/", views.gestion_modeles, name="gestion_modeles"),
    path("gestion/referentiel/", views.gestion_referentiel, name="gestion_referentiel"),
    path("gestion/user/", views.gestion_user),
    path("gestion/pipeline/", views.gestion_pipeline),
    path("gestion/pipeline/<int:pk>/", views.gestion_pipeline_status),
    path("gestion/meteo/", views.gestion_meteo),
    path("gestion/profils/", views.gestion_profils),
    path("gestion/tarifs/", views.gestion_tarifs),
]
