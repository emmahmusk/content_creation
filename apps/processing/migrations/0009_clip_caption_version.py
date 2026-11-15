from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("processing", "0008_durable_clip_exports"),
    ]

    operations = [
        migrations.AddField(
            model_name="clip",
            name="caption_version",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
