from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("foyer/", views.foyer_page, name="foyer"),
    path("gestion/", views.gestion_page, name="gestion"),
    path("gestion/user/", views.gestion_user),
    path("gestion/action/", views.gestion_action),
    path("operateur/", views.operateur_page, name="operateur"),
]
