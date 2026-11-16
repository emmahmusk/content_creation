from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("deliverables", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deliverable",
            name="kind",
            field=models.CharField(
                choices=[
                    ("clip_plan", "Clip suggestions"),
                    ("captions_hooks", "Captions and hooks"),
                    ("social_posts", "Social posts"),
                    ("youtube_package", "YouTube package"),
                    ("newsletter", "Newsletter / article"),
                    ("clean_audio", "Cleaned audio"),
                    ("other", "Other"),
                ],
                max_length=30,
            ),
        ),
    ]
