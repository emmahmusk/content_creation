import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("processing", "0005_clip_editing_instructions")]

    operations = [
        migrations.CreateModel(
            name="BrollPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(max_length=20)),
                ("intensity", models.CharField(max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("planning", "Planning"), ("ready", "Ready"), ("partial", "Partially generated"), ("skipped", "Skipped"), ("failed", "Failed")], default="pending", max_length=20)),
                ("scenes", models.JSONField(blank=True, default=list)),
                ("provider", models.CharField(default="NVIDIA NIM", max_length=80)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("clip", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="broll_plan", to="processing.clip")),
            ],
            options={"ordering": ["clip__rank"]},
        )
    ]
