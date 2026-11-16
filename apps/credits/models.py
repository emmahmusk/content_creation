import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class CreditPlan(models.Model):
    class Currency(models.TextChoices):
        NGN = "NGN", "Nigerian naira"
        USD = "USD", "US dollar"

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    credits = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price_ngn = models.PositiveIntegerField(default=0, help_text="Whole naira. Keep at 0 until this plan is priced.")
    price_usd = models.DecimalField(max_digits=9, decimal_places=2, default=0, help_text="US dollars. Keep at 0 until this plan is priced.")
    max_source_mb = models.PositiveIntegerField(default=0, help_text="Maximum upload size. Set 0 for no plan-specific cap.")
    max_source_minutes = models.PositiveIntegerField(default=0, help_text="Maximum source duration. Set 0 for no plan-specific cap.")
    max_clips_per_order = models.PositiveSmallIntegerField(default=3)
    selar_url = models.URLField(blank=True, help_text="Selar product page for this tier.")
    qr_code = models.FileField(
        upload_to="credit_qr/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp"])],
        help_text="Optional QR image for this tier. PNG, JPG, or WebP.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    recommended = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "credits", "name"]

    def __str__(self):
        return self.name

    def price_for(self, currency):
        if currency == self.Currency.NGN:
            return self.price_ngn
        return self.price_usd

    @property
    def purchasable(self):
        return bool(self.is_active and self.credits and self.selar_url and self.price_ngn and self.price_usd)


class PaymentRequest(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Checkout started"
        AWAITING_REVIEW = "awaiting_review", "Payment submitted"
        APPROVED = "approved", "Credits added"
        DECLINED = "declined", "Payment needs attention"

    class Currency(models.TextChoices):
        NGN = "NGN", "NGN"
        USD = "USD", "USD"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_payment_requests")
    plan = models.ForeignKey(CreditPlan, on_delete=models.PROTECT, related_name="payment_requests")
    plan_name = models.CharField(max_length=80)
    credits = models.PositiveIntegerField()
    max_source_mb = models.PositiveIntegerField(default=0)
    max_source_minutes = models.PositiveIntegerField(default=0)
    max_clips_per_order = models.PositiveSmallIntegerField(default=3)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    selar_url = models.URLField()
    payment_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_credit_payments")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.plan_name} · {self.user} · {self.get_status_display()}"

    @transaction.atomic
    def approve(self, reviewer, note=""):
        request = PaymentRequest.objects.select_for_update().get(pk=self.pk)
        if request.status != self.Status.AWAITING_REVIEW:
            return False
        CreditLedgerEntry.objects.get_or_create(
            payment_request=request,
            entry_type=CreditLedgerEntry.Type.PURCHASE,
            defaults={
                "user": request.user,
                "amount": request.credits,
                "description": f"{request.plan_name} credits",
                "created_by": reviewer,
            },
        )
        request.status = self.Status.APPROVED
        request.reviewed_by = reviewer
        request.reviewed_at = timezone.now()
        request.admin_note = note
        request.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note"])
        self.status = request.status
        self.reviewed_by = reviewer
        self.reviewed_at = request.reviewed_at
        self.admin_note = note
        return True

    @transaction.atomic
    def decline(self, reviewer, note=""):
        request = PaymentRequest.objects.select_for_update().get(pk=self.pk)
        if request.status != self.Status.AWAITING_REVIEW:
            return False
        request.status = self.Status.DECLINED
        request.reviewed_by = reviewer
        request.reviewed_at = timezone.now()
        request.admin_note = note
        request.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note"])
        self.status = request.status
        self.reviewed_by = reviewer
        self.reviewed_at = request.reviewed_at
        self.admin_note = note
        return True


class CreditReservation(models.Model):
    class Kind(models.TextChoices):
        ANALYSIS = "analysis", "Source analysis"
        RENDER = "render", "Clip rendering"

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        CAPTURED = "captured", "Charged"
        RELEASED = "released", "Released"

    pipeline = models.ForeignKey(
        "processing.PipelineRun",
        on_delete=models.CASCADE,
        related_name="credit_reservations",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    attempt = models.PositiveSmallIntegerField(default=1)
    credits = models.PositiveIntegerField()
    charged_credits = models.PositiveIntegerField(default=0)
    usage_items = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RESERVED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline", "kind", "attempt"],
                name="unique_pipeline_credit_reservation",
            ),
        ]

    def __str__(self):
        return f"{self.kind} · {self.credits} credits · {self.get_status_display()}"


class CreditLedgerEntry(models.Model):
    class Type(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        WELCOME = "welcome", "Welcome credits"
        GIFT = "gift", "Free gift"
        ADJUSTMENT = "adjustment", "Admin adjustment"
        SPEND = "spend", "Usage"
        REFUND = "refund", "Refund"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_ledger_entries")
    payment_request = models.ForeignKey(PaymentRequest, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True)
    reservation = models.OneToOneField(CreditReservation, on_delete=models.PROTECT, related_name="ledger_entry", null=True, blank=True)
    entry_type = models.CharField(max_length=16, choices=Type.choices)
    amount = models.IntegerField(help_text="Positive adds credits; negative spends credits.")
    description = models.CharField(max_length=180)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_entries_created")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["payment_request", "entry_type"], name="unique_credit_purchase_per_payment"),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(entry_type="welcome"),
                name="unique_welcome_credit_grant_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.amount:+} credits · {self.user} · {self.entry_type}"
