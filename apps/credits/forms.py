from django import forms

from .models import PaymentRequest


class PaymentConfirmationForm(forms.Form):
    payment_reference = forms.CharField(
        max_length=120,
        label="Selar payment reference",
        help_text="Copy the transaction reference shown on your Selar receipt.",
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "e.g. SELAR-123456"}),
    )
    confirm = forms.BooleanField(
        label="I have completed payment for the amount shown above.",
        required=True,
    )

    def save(self, payment_request):
        payment_request.payment_reference = self.cleaned_data["payment_reference"].strip()
        payment_request.status = PaymentRequest.Status.AWAITING_REVIEW
        from django.utils import timezone
        payment_request.submitted_at = timezone.now()
        payment_request.save(update_fields=["payment_reference", "status", "submitted_at"])
        return payment_request
