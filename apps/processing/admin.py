from django.contrib import admin
from .models import Clip, ContentIntelligence, LearningSignal, PipelineRun, PublicationJob, RepurposeAsset, StageRun, TranscriptSegment
class StageInline(admin.TabularInline):
    model=StageRun; extra=0; readonly_fields=("name","status","attempts","error","started_at","finished_at")
@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display=("order","status","current_stage","progress","created_at"); list_filter=("status","current_stage"); inlines=[StageInline]
@admin.register(Clip)
class ClipAdmin(admin.ModelAdmin):
    list_display=("rank","title","order","status","score"); list_filter=("status",); search_fields=("title","order__title")
admin.site.register(TranscriptSegment)
admin.site.register(ContentIntelligence)
admin.site.register(RepurposeAsset)
admin.site.register(PublicationJob)
admin.site.register(LearningSignal)
