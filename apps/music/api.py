from rest_framework import decorators, permissions, response, status, viewsets

from .models import AfroStudioProject, StudioAsset
from .serializers import AfroStudioProjectSerializer, CreativeDirectionSerializer, LyricsUpdateSerializer
from .tasks import dispatch_analysis, dispatch_generation


class AfroStudioProjectViewSet(viewsets.ModelViewSet):
    serializer_class = AfroStudioProjectSerializer
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        return AfroStudioProject.objects.filter(owner=self.request.user).prefetch_related("assets")

    def perform_create(self, serializer):
        audio = serializer.validated_data["reference_audio"]
        project = serializer.save(owner=self.request.user, original_filename=audio.name)
        dispatch_analysis(project.id)

    def partial_update(self, request, *args, **kwargs):
        return response.Response(
            {"detail": "Use the dedicated direction or lyrics action for project changes."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @decorators.action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        project = self.get_object()
        if project.status != AfroStudioProject.Status.FAILED:
            return response.Response({"detail": "Only failed projects can be retried."}, status=status.HTTP_409_CONFLICT)
        if project.creative_direction and project.current_stage in {
            AfroStudioProject.Stage.CREATIVE_PLAN,
            AfroStudioProject.Stage.LYRICS,
            AfroStudioProject.Stage.REVIEW,
        }:
            dispatch_generation(project.id)
            detail = "Original song generation restarted."
        else:
            dispatch_analysis(project.id)
            detail = "Analysis restarted."
        return response.Response({"detail": detail}, status=status.HTTP_202_ACCEPTED)

    @decorators.action(detail=True, methods=["post"])
    def direction(self, request, pk=None):
        project = self.get_object()
        if project.status not in {AfroStudioProject.Status.DIRECTION, AfroStudioProject.Status.REVIEW}:
            return response.Response({"detail": "Finish the music analysis before setting creative direction."}, status=status.HTTP_409_CONFLICT)
        serializer = CreativeDirectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project.creative_direction = serializer.validated_data
        project.save(update_fields=["creative_direction", "updated_at"])
        dispatch_generation(project.id)
        return response.Response(AfroStudioProjectSerializer(project, context={"request": request}).data, status=status.HTTP_202_ACCEPTED)

    @decorators.action(detail=True, methods=["patch", "post"])
    def lyrics(self, request, pk=None):
        project = self.get_object()
        if project.status != AfroStudioProject.Status.REVIEW:
            return response.Response({"detail": "Lyrics become editable when the project reaches studio review."}, status=status.HTTP_409_CONFLICT)
        serializer = LyricsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project.lyrics = serializer.validated_data["lyrics"]
        project.save(update_fields=["lyrics", "updated_at"])
        StudioAsset.objects.update_or_create(
            project=project,
            kind=StudioAsset.Kind.LYRICS,
            defaults={"label": "Original lyrics", "text_content": project.lyrics},
        )
        return response.Response({"lyrics": project.lyrics, "detail": "Lyrics saved."})

    @decorators.action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        project = self.get_object()
        return response.Response({
            "status": project.status,
            "stage": project.current_stage,
            "stage_label": project.get_current_stage_display(),
            "progress": project.progress,
            "error": project.error_message,
        })
