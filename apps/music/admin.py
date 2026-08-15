from django.contrib import admin

from .models import AfroStudioProject, StudioAsset


class StudioAssetInline(admin.TabularInline):
    model = StudioAsset
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(AfroStudioProject)
class AfroStudioProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "current_stage", "progress", "created_at")
    list_filter = ("status", "current_stage")
    search_fields = ("title", "owner__username")
    readonly_fields = ("created_at", "updated_at", "analyzed_at", "generated_at")
    inlines = (StudioAssetInline,)
