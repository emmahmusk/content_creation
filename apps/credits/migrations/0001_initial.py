# Generated for the first manual Selar payment and clipping-credit ledger release.
import uuid

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="CreditPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("slug", models.SlugField(unique=True)),
                ("tagline", models.CharField(blank=True, max_length=160)),
                ("description", models.TextField(blank=True)),
                ("credits", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("price_ngn", models.PositiveIntegerField(default=0, help_text="Whole naira. Keep at 0 until this plan is priced.")),
                ("price_usd", models.DecimalField(decimal_places=2, default=0, max_digits=9, help_text="US dollars. Keep at 0 until this plan is priced.")),
                ("max_source_mb", models.PositiveIntegerField(default=0, help_text="Maximum upload size. Set 0 for no plan-specific cap.")),
                ("max_source_minutes", models.PositiveIntegerField(default=0, help_text="Maximum source duration. Set 0 for no plan-specific cap.")),
                ("max_clips_per_order", models.PositiveSmallIntegerField(default=3)),
                ("selar_url", models.URLField(blank=True, help_text="Selar product page for this tier.")),
                ("qr_code", models.FileField(blank=True, upload_to="credit_qr/", validators=[django.core.validators.FileExtensionValidator(["png", "jpg", "jpeg", "webp"])])),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("recommended", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "credits", "name"]},
        ),
        migrations.CreateModel(
            name="PaymentRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("plan_name", models.CharField(max_length=80)),
                ("credits", models.PositiveIntegerField()),
                ("max_source_mb", models.PositiveIntegerField(default=0)),
                ("max_source_minutes", models.PositiveIntegerField(default=0)),
                ("max_clips_per_order", models.PositiveSmallIntegerField(default=3)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(choices=[("NGN", "NGN"), ("USD", "USD")], max_length=3)),
                ("selar_url", models.URLField()),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("status", models.CharField(choices=[("awaiting_payment", "Awaiting payment"), ("awaiting_review", "Awaiting admin review"), ("approved", "Approved"), ("declined", "Declined")], db_index=True, default="awaiting_payment", max_length=24)),
                ("admin_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="credits.creditplan")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_credit_payments", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="credit_payment_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CreditLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_type", models.CharField(choices=[("purchase", "Purchase"), ("adjustment", "Admin adjustment"), ("spend", "Usage"), ("refund", "Refund")], max_length=16)),
                ("amount", models.IntegerField(help_text="Positive adds credits; negative spends credits.")),
                ("description", models.CharField(max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="credit_entries_created", to=settings.AUTH_USER_MODEL)),
                ("payment_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="credits.paymentrequest")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="credit_ledger_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.AddConstraint(
            model_name="creditledgerentry",
            constraint=models.UniqueConstraint(fields=("payment_request", "entry_type"), name="unique_credit_purchase_per_payment"),
        ),
    ]
