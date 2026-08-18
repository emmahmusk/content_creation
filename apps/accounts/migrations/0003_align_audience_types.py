from django.db import migrations, models


def align_existing_audiences(apps, schema_editor):
    profile = apps.get_model("accounts", "CustomerProfile")
    profile.objects.filter(audience_type="podcaster").update(audience_type="creator_library")
    profile.objects.filter(audience_type__in=["coach", "church", "consultant", "youtube"]).update(
        audience_type="creator_library"
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_socialhandle")]

    operations = [
        migrations.RunPython(align_existing_audiences, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="customerprofile",
            name="audience_type",
            field=models.CharField(
                choices=[
                    ("clipping_agency", "Clipping agency"),
                    ("high_volume_clipper", "High-volume clipper"),
                    ("podcast_agency", "Podcast clipping agency"),
                    ("social_agency", "Social media agency"),
                    ("creator_library", "Creator with a content library"),
                    ("course_community", "Clipping course or community"),
                    ("beginner_clipper", "Individual beginner clipper"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=32,
            ),
        ),
    ]
