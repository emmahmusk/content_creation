from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("credits", "0005_alter_creditledgerentry_entry_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditledgerentry",
            name="entry_type",
            field=models.CharField(
                choices=[
                    ("purchase", "Purchase"),
                    ("welcome", "Welcome credits"),
                    ("gift", "Free gift"),
                    ("adjustment", "Admin adjustment"),
                    ("spend", "Usage"),
                    ("refund", "Refund"),
                ],
                max_length=16,
            ),
        ),
    ]
