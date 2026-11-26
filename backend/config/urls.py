from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "ÉnergiTN · administration technique"
admin.site.site_title = "ÉnergiTN"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("web.urls")),
]
handler404 = "web.views.not_found"
