from django.contrib import admin
from .models import Deliverable
@admin.register(Deliverable)
class DeliverableAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "kind", "status", "version", "updated_at")
    list_filter = ("kind", "status")
    search_fields = ("title", "order__title")
