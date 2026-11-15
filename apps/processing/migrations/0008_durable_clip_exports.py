from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("processing", "0007_pipelinerun_youtube_auth"),
    ]

    operations = [
        migrations.AddField(
            model_name="clip",
            name="cloudinary_video_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_video_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_audio_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_audio_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_subtitle_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_subtitle_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_thumbnail_public_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="clip",
            name="cloudinary_thumbnail_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="storage_recovery",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="recovery_clip_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
