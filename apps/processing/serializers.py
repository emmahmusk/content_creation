from rest_framework import serializers
from .models import BrollPlan, Clip, ContentIntelligence, LearningSignal, PipelineRun, PublicationJob, RepurposeAsset, StageRun, TranscriptSegment
class StageRunSerializer(serializers.ModelSerializer):
    class Meta: model=StageRun; fields=["name","status","attempts","metadata","error","started_at","finished_at"]
class PipelineRunSerializer(serializers.ModelSerializer):
    stages=StageRunSerializer(many=True,read_only=True)
    class Meta: model=PipelineRun; fields=["id","order","status","current_stage","progress","error","started_at","finished_at","created_at","stages"]
class BrollPlanSerializer(serializers.ModelSerializer):
    class Meta: model=BrollPlan; fields=["mode","intensity","status","scenes","provider","error","updated_at"]
class ClipSerializer(serializers.ModelSerializer):
    duration_seconds=serializers.FloatField(read_only=True)
    broll_plan=BrollPlanSerializer(read_only=True)
    class Meta: model=Clip; fields=["id","order","rank","title","hook","caption","start_ms","end_ms","duration_seconds","score","rationale","preview_url","editing_instructions","broll_plan","video","audio","subtitle","thumbnail","status"]
class TranscriptSegmentSerializer(serializers.ModelSerializer):
    class Meta: model=TranscriptSegment; fields=["id","order","start_ms","end_ms","text","words","speaker"]

class RepurposeAssetSerializer(serializers.ModelSerializer):
    kind_label=serializers.CharField(source="get_kind_display",read_only=True)
    class Meta: model=RepurposeAsset; fields=["id","clip","kind","kind_label","title","content","metadata","version","updated_at"];read_only_fields=["clip","kind","version"]

class ContentIntelligenceSerializer(serializers.ModelSerializer):
    repurpose_assets=RepurposeAssetSerializer(source="clip.repurpose_assets",many=True,read_only=True)
    class Meta: model=ContentIntelligence; fields=["id","clip","status","content_dna","selection_reasoning","platform_strategy","business_impact","audience_matching","semantic_graph","editor_recommendations","confidence","model","error","version","updated_at","repurpose_assets"]

class PublicationJobSerializer(serializers.ModelSerializer):
    platform=serializers.CharField(source="social_handle.platform",read_only=True)
    account_label=serializers.CharField(source="social_handle.handle",read_only=True)
    class Meta: model=PublicationJob; fields=["id","clip","social_handle","platform","account_label","action","status","scheduled_for","platform_payload","external_id","error","created_at","updated_at"];read_only_fields=["status","external_id","error"]
    def validate(self,attrs):
        user=self.context["request"].user;clip=attrs.get("clip");handle=attrs.get("social_handle");action=attrs.get("action")
        if clip.order.customer_id != user.id or handle.user_id != user.id: raise serializers.ValidationError("The clip and destination must belong to your account.")
        if action==PublicationJob.Action.SCHEDULE and not attrs.get("scheduled_for"): raise serializers.ValidationError({"scheduled_for":"Choose a publishing time."})
        if action in {PublicationJob.Action.PUBLISH,PublicationJob.Action.REPUBLISH}: raise serializers.ValidationError({"action":"Connect an authenticated platform account before publishing directly. Saved handles can currently be used for drafts, queues, and schedules."})
        return attrs
    def create(self,validated_data):
        action=validated_data["action"];status={PublicationJob.Action.DRAFT:PublicationJob.Status.DRAFT,PublicationJob.Action.QUEUE:PublicationJob.Status.QUEUED,PublicationJob.Action.SCHEDULE:PublicationJob.Status.SCHEDULED}.get(action,PublicationJob.Status.DRAFT)
        return PublicationJob.objects.create(user=self.context["request"].user,status=status,**validated_data)

class LearningSignalSerializer(serializers.ModelSerializer):
    class Meta: model=LearningSignal; fields=["id","clip","publication","event_type","value","metadata","created_at"]
    def validate_clip(self,clip):
        if clip.order.customer_id != self.context["request"].user.id: raise serializers.ValidationError("This clip does not belong to your account.")
        return clip
