import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AfroStudioProject",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=160)),
                ("reference_audio", models.FileField(upload_to="music/references/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(["mp3", "wav", "flac", "aac", "m4a"])])),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("source_rights_confirmed", models.BooleanField(default=False)),
                ("analysis_only_confirmed", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("analyzing", "Analyzing reference"), ("direction", "Creative direction"), ("generating", "Creating original concept"), ("review", "Studio review"), ("failed", "Needs attention")], db_index=True, default="draft", max_length=24)),
                ("current_stage", models.CharField(choices=[("upload", "Upload"), ("audio_intelligence", "Audio intelligence"), ("music_report", "Music report"), ("creative_plan", "Creative plan"), ("lyrics", "Original lyrics"), ("review", "Studio review")], default="upload", max_length=32)),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("audio_metadata", models.JSONField(blank=True, default=dict)),
                ("intelligence", models.JSONField(blank=True, default=dict)),
                ("creative_direction", models.JSONField(blank=True, default=dict)),
                ("creative_plan", models.JSONField(blank=True, default=dict)),
                ("lyrics", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("analyzed_at", models.DateTimeField(blank=True, null=True)),
                ("generated_at", models.DateTimeField(blank=True, null=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="afrofusion_projects", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StudioAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("lyrics", "Lyrics"), ("project_json", "Project data"), ("melody_json", "Melody plan"), ("midi", "MIDI"), ("audio", "Audio preview"), ("stem", "Stem")], max_length=24)),
                ("label", models.CharField(max_length=120)),
                ("file", models.FileField(blank=True, upload_to="music/exports/%Y/%m/")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("text_content", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="music.afrostudioproject")),
            ],
            options={"ordering": ["kind", "created_at"]},
        ),
        migrations.AddIndex(model_name="afrostudioproject", index=models.Index(fields=["owner", "status"], name="music_afros_owner_i_7ce40b_idx")),
    ]
