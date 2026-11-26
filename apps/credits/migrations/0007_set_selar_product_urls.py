from django.db import migrations


SELAR_URLS = {
    "hobby": "https://selar.com/kraftaa-hobby",
    "creator": "https://selar.com/kraftaa-creator",
    "pro": "https://selar.com/kraftaa-pro",
    "studio": "https://selar.com/kraftaa-studio",
}


def set_selar_product_urls(apps, schema_editor):
    CreditPlan = apps.get_model("credits", "CreditPlan")
    for slug, url in SELAR_URLS.items():
        CreditPlan.objects.filter(slug=slug).update(selar_url=url)


def clear_selar_product_urls(apps, schema_editor):
    CreditPlan = apps.get_model("credits", "CreditPlan")
    CreditPlan.objects.filter(slug__in=SELAR_URLS).update(selar_url="")


class Migration(migrations.Migration):
    dependencies = [
        ("credits", "0006_creditledgerentry_gift_type"),
    ]

    operations = [
        migrations.RunPython(set_selar_product_urls, clear_selar_product_urls),
    ]
