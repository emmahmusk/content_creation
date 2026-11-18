from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0007_contentorder_include_captions")]
    operations = [
        migrations.AddField(
            model_name="sourceasset", name="imported_file",
            field=models.FileField(upload_to="imports/youtube/%Y/%m/", blank=True),
        ),
        migrations.AddField(
            model_name="sourceasset", name="youtube_imported_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
