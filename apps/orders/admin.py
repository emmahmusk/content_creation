from django.contrib import admin
from .models import ContentOrder, OrderEvent, SourceAsset

class SourceAssetInline(admin.TabularInline):
    model = SourceAsset; extra = 0
class OrderEventInline(admin.TabularInline):
    model = OrderEvent; extra = 0; readonly_fields = ("created_at",)
@admin.register(ContentOrder)
class ContentOrderAdmin(admin.ModelAdmin):
    list_display = ("title", "customer", "status", "due_at", "created_at")
    list_filter = ("status", "include_audio_cleanup", "broll_mode", "broll_intensity")
    search_fields = ("title", "customer__username", "customer__email")
    inlines = [SourceAssetInline, OrderEventInline]
admin.site.register(SourceAsset)
admin.site.register(OrderEvent)
