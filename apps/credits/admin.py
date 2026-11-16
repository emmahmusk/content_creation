from django.contrib import admin, messages
from django.db import transaction
from django import forms

from .models import CreditLedgerEntry, CreditPlan, CreditReservation, PaymentRequest


class CreditGiftAdminForm(forms.ModelForm):
    amount = forms.IntegerField(
        min_value=1,
        label="Credits to gift",
        help_text="Gifted credits are added to the user’s available clip wallet.",
    )
    description = forms.CharField(
        label="Gift note shown in wallet history",
        max_length=180,
        required=False,
        initial="A gift from Kraftaa",
        help_text="The user will also see this entry marked as a free gift.",
    )

    class Meta:
        model = CreditLedgerEntry
        fields = ("user", "amount", "description")

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip() or "A gift from Kraftaa"


@admin.register(CreditPlan)
class CreditPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "credits", "price_ngn", "price_usd", "max_source_mb", "max_clips_per_order", "is_active", "recommended")
    list_filter = ("is_active", "recommended")
    search_fields = ("name", "slug", "selar_url")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "plan_name", "amount", "currency", "credits", "payment_reference", "status", "reviewed_by")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__username", "user__email", "payment_reference", "plan_name", "id")
    readonly_fields = ("user", "plan", "plan_name", "credits", "max_source_mb", "max_source_minutes", "max_clips_per_order", "amount", "currency", "selar_url", "payment_reference", "status", "created_at", "submitted_at", "reviewed_at", "reviewed_by")
    actions = ("approve_payments", "decline_payments")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("approve_payments", None)
            actions.pop("decline_payments", None)
        return actions

    def has_add_permission(self, request):
        return False

    @admin.action(description="Approve selected payments and grant plan credits")
    def approve_payments(self, request, queryset):
        approved = 0
        with transaction.atomic():
            for payment in queryset.select_for_update():
                approved += int(payment.approve(request.user, payment.admin_note))
        self.message_user(request, f"Approved {approved} payment(s); credits were added once per payment.", messages.SUCCESS)

    @admin.action(description="Decline selected payments (no credits granted)")
    def decline_payments(self, request, queryset):
        declined = 0
        with transaction.atomic():
            for payment in queryset.select_for_update():
                declined += int(payment.decline(request.user, payment.admin_note))
        self.message_user(request, f"Declined {declined} payment(s); no credits were granted.", messages.WARNING)


@admin.register(CreditLedgerEntry)
class CreditLedgerEntryAdmin(admin.ModelAdmin):
    change_list_template = "admin/credits/creditledgerentry/change_list.html"
    list_display = ("created_at", "user", "entry_type", "amount", "description", "payment_request", "created_by")
    list_filter = ("entry_type", "created_at")
    search_fields = ("user__username", "user__email", "description")
    autocomplete_fields = ("user",)
    form = CreditGiftAdminForm
    readonly_fields = ("user", "payment_request", "reservation", "entry_type", "amount", "description", "created_by", "created_at")

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("user", "amount", "description")
        return self.readonly_fields

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.readonly_fields

    def has_add_permission(self, request):
        return request.user.is_superuser

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "title": "Grant clip credits as a gift"}
        return super().add_view(request, form_url, extra_context)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.entry_type = CreditLedgerEntry.Type.GIFT
            obj.created_by = request.user
            obj.description = form.cleaned_data.get("description", "A gift from Kraftaa")[:180]
        super().save_model(request, obj, form, change)
        if not change:
            self.message_user(
                request,
                f"Gifted {obj.amount} clipping credits to {obj.user}.",
                messages.SUCCESS,
            )


@admin.register(CreditReservation)
class CreditReservationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "pipeline", "kind", "attempt", "credits", "charged_credits", "status", "settled_at")
    list_filter = ("kind", "status", "created_at")
    search_fields = ("pipeline__order__title", "pipeline__order__customer__username", "pipeline__order__customer__email")
    readonly_fields = ("pipeline", "kind", "attempt", "credits", "charged_credits", "usage_items", "status", "created_at", "settled_at")
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
