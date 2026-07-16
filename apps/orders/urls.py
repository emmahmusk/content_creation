from django.urls import path
from . import views
app_name = "orders"
urlpatterns = [path("", views.dashboard, name="dashboard"), path("new/", views.create_order, name="create"), path("<uuid:pk>/", views.order_detail, name="detail")]
