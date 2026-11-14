from django.urls import path

from . import views

app_name = "credits"
urlpatterns = [
    path("", views.pricing, name="pricing"),
    path("buy/<slug:plan_slug>/", views.start_purchase, name="start"),
    path("payment/<uuid:payment_id>/", views.payment_detail, name="payment"),
    path("wallet/", views.wallet, name="wallet"),
]
