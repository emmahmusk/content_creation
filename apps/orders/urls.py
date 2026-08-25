from django.urls import path
from . import views
app_name = "orders"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new/", views.create_order, name="create"),
    path("<uuid:pk>/", views.order_detail, name="detail"),
    path("<uuid:pk>/edit/", views.edit_order, name="edit"),
    path("<uuid:pk>/replace-source/", views.replace_blocked_source, name="replace-source"),
    path("<uuid:pk>/stop-analysis/", views.stop_analysis_for_edit, name="stop-analysis"),
]
