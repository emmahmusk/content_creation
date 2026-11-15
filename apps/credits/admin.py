from django.contrib import admin, messages
from django.db import transaction

from .models import CreditLedgerEntry, CreditPlan, CreditReservation, PaymentRequest


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
    list_display = ("created_at", "user", "entry_type", "amount", "description", "payment_request", "created_by")
    list_filter = ("entry_type", "created_at")
    search_fields = ("user__username", "user__email", "description")
    readonly_fields = ("user", "payment_request", "reservation", "entry_type", "amount", "description", "created_by", "created_at")
    def has_add_permission(self, request):
        return request.user.is_superuser


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
