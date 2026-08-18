from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_sourceasset_rights_confirmed")]

    operations = [
        migrations.AddField(
            model_name="contentorder",
            name="broll_mode",
            field=models.CharField(
                choices=[
                    ("none", "No B-roll"),
                    ("ai_selected", "AI-selected B-roll"),
                    ("ai_generated", "AI-generated B-roll"),
                    ("hybrid", "Stock + AI-generated B-roll"),
                ],
                default="none",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contentorder",
            name="broll_intensity",
            field=models.CharField(
                choices=[
                    ("minimal", "Minimal"),
                    ("moderate", "Moderate"),
                    ("aggressive", "Aggressive"),
                ],
                default="moderate",
                max_length=20,
            ),
        ),
    ]
