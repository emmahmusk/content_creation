from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_launch_plans(apps, schema_editor):
    CreditPlan = apps.get_model("credits", "CreditPlan")
    plans = [
        {
            "name": "Hobby", "slug": "hobby", "tagline": "Try your first few batches.",
            "description": "About 5 standard batches: each example batch is a 30-minute source and 3 clips up to 60 seconds.",
            "credits": 20, "price_ngn": 7000, "price_usd": "5.00", "max_source_mb": 2048,
            "max_clips_per_order": 10, "sort_order": 1,
        },
        {
            "name": "Creator", "slug": "creator", "tagline": "For a steady clipping rhythm.",
            "description": "About 25 standard batches: each example batch is a 30-minute source and 3 clips up to 60 seconds.",
            "credits": 100, "price_ngn": 35000, "price_usd": "25.00", "max_source_mb": 2048,
            "max_clips_per_order": 10, "sort_order": 2, "recommended": True,
        },
        {
            "name": "Pro", "slug": "pro", "tagline": "For regular multi-video production.",
            "description": "About 75 standard batches: each example batch is a 30-minute source and 3 clips up to 60 seconds.",
            "credits": 300, "price_ngn": 105000, "price_usd": "75.00", "max_source_mb": 2048,
            "max_clips_per_order": 10, "sort_order": 3,
        },
        {
            "name": "Studio", "slug": "studio", "tagline": "For high-volume clipping work.",
            "description": "About 250 standard batches: each example batch is a 30-minute source and 3 clips up to 60 seconds.",
            "credits": 1000, "price_ngn": 350000, "price_usd": "250.00", "max_source_mb": 2048,
            "max_clips_per_order": 10, "sort_order": 4,
        },
    ]
    for plan in plans:
        CreditPlan.objects.update_or_create(slug=plan["slug"], defaults={**plan, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [
        ("credits", "0002_alter_creditplan_qr_code"),
        ("processing", "0007_pipelinerun_youtube_auth"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CreditReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("analysis", "Source analysis"), ("render", "Clip rendering")], max_length=16)),
                ("attempt", models.PositiveSmallIntegerField(default=1)),
                ("credits", models.PositiveIntegerField()),
                ("charged_credits", models.PositiveIntegerField(default=0)),
                ("usage_items", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("reserved", "Reserved"), ("captured", "Charged"), ("released", "Released")], db_index=True, default="reserved", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credit_reservations", to="processing.pipelinerun")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="creditledgerentry",
            name="reservation",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entry", to="credits.creditreservation"),
        ),
        migrations.AddConstraint(
            model_name="creditreservation",
            constraint=models.UniqueConstraint(fields=("pipeline", "kind", "attempt"), name="unique_pipeline_credit_reservation"),
        ),
        migrations.RunPython(seed_launch_plans, migrations.RunPython.noop),
    ]
