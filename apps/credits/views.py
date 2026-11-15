from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import PaymentConfirmationForm
from .models import CreditPlan, PaymentRequest
from .services import available_balance


def pricing(request):
    plans = CreditPlan.objects.filter(is_active=True)
    return render(request, "credits/pricing.html", {
        "plans": plans,
        "credit_rate_ngn": settings.CLIPPING_CREDIT_RATE_NGN,
        "credit_rate_usd": settings.CLIPPING_CREDIT_RATE_USD,
    })


@require_http_methods(["POST"])
def start_purchase(request, plan_slug):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    plan = get_object_or_404(CreditPlan, slug=plan_slug, is_active=True)
    if not plan.purchasable:
        raise Http404("This credit plan is not available for purchase.")
    currency = request.POST.get("currency", "NGN")
    if currency not in CreditPlan.Currency.values:
        messages.error(request, "Choose NGN or USD to continue.")
        return redirect("credits:pricing")
    price = plan.price_for(currency)
    payment = PaymentRequest.objects.create(
        user=request.user,
        plan=plan,
        plan_name=plan.name,
        credits=plan.credits,
        max_source_mb=plan.max_source_mb,
        max_source_minutes=plan.max_source_minutes,
        max_clips_per_order=plan.max_clips_per_order,
        amount=Decimal(price),
        currency=currency,
        selar_url=plan.selar_url,
    )
    return redirect("credits:payment", payment_id=payment.pk)


@login_required
@require_http_methods(["GET", "POST"])
def payment_detail(request, payment_id):
    payment = get_object_or_404(PaymentRequest, pk=payment_id, user=request.user)
    form = PaymentConfirmationForm(request.POST or None)
    if request.method == "POST":
        if payment.status != PaymentRequest.Status.AWAITING_PAYMENT:
            messages.info(request, "This payment request has already been submitted for review.")
            return redirect("credits:payment", payment_id=payment.pk)
        if form.is_valid():
            form.save(payment)
            messages.success(request, "Payment submitted. Credits will appear after our team verifies the transaction.")
            return redirect("credits:wallet")
    return render(request, "credits/payment.html", {"payment": payment, "form": form})


@login_required
def wallet(request):
    entries = request.user.credit_ledger_entries.select_related("created_by", "payment_request")[:30]
    payments = request.user.credit_payment_requests.select_related("plan")[:20]
    return render(request, "credits/wallet.html", {
        "balance": available_balance(request.user),
        "entries": entries,
        "payments": payments,
        "now": timezone.now(),
    })
