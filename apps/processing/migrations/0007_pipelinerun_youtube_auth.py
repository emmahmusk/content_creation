from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("processing", "0006_brollplan"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinerun",
            name="youtube_auth_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="youtube_auth_code",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="youtube_auth_confirmed",
            field=models.BooleanField(default=False),
        ),
    ]
