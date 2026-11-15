from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.contrib.staticfiles.views import serve as serve_static
from core import views

urlpatterns = [
    path("health/", views.health_check),
    path("admin/", admin.site.urls),
    path("login", views.login_view), path("registro", views.register), path("logout", views.logout_view),
    path("", views.dashboard), path("finanzas", views.finance),
    path("finanzas/egresos", views.finance), path("finanzas/ingresos", views.income_create),
    path("finanzas/egresos/registrar", views.expense_create), path("finanzas/egresos/editar", views.expense_edit), path("finanzas/egresos/eliminar", views.expense_delete), path("finanzas/ingresos/editar", views.income_edit), path("finanzas/ingresos/eliminar", views.income_delete), path("finanzas/exportar", views.export),
    path("finanzas/exportar-ingresos", views.export), path("finanzas/comprobantes", views.receipts),
    path("proyectos/fases", views.project_phases), path("proyectos/dashboard", views.projects),
    path("proyectos", views.projects), path("proyectos/guardar", views.project_save), path("proyectos/eliminar", views.project_delete),
    path("drive", views.assets), path("assets", views.assets), path("assets/upload", views.asset_upload), path("assets/replace", views.asset_replace), path("assets/preview", views.asset_preview), path("assets/preview/file", views.asset_preview_file), path("assets/restore", views.asset_restore), path("assets/download", views.asset_download), path("assets/delete", views.asset_delete),
    path("presidencia", views.presidency), path("recursos-humanos", views.human_resources), path("usuarios", views.users), path("roles", views.roles),
]

# runserver sirve los estáticos locales independientemente del modo DEBUG.
if settings.SERVE_STATIC:
    urlpatterns.insert(0, re_path(r"^static/(?P<path>.*)$", serve_static, {"insecure": True}))

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
