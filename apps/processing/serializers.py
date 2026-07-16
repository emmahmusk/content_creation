from rest_framework import serializers
from .models import Clip, PipelineRun, StageRun, TranscriptSegment
class StageRunSerializer(serializers.ModelSerializer):
    class Meta: model=StageRun; fields=["name","status","attempts","metadata","error","started_at","finished_at"]
class PipelineRunSerializer(serializers.ModelSerializer):
    stages=StageRunSerializer(many=True,read_only=True)
    class Meta: model=PipelineRun; fields=["id","order","status","current_stage","progress","error","started_at","finished_at","created_at","stages"]
class ClipSerializer(serializers.ModelSerializer):
    duration_seconds=serializers.FloatField(read_only=True)
    class Meta: model=Clip; fields=["id","order","rank","title","hook","caption","start_ms","end_ms","duration_seconds","score","rationale","video","subtitle","thumbnail","status"]
class TranscriptSegmentSerializer(serializers.ModelSerializer):
    class Meta: model=TranscriptSegment; fields=["id","order","start_ms","end_ms","text","words","speaker"]
