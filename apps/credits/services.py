from math import ceil

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import CreditLedgerEntry, CreditReservation


class InsufficientCredits(Exception):
    def __init__(self, required, available):
        self.required = required
        self.available = available
        super().__init__(
            f"This job needs {required} credits, but your available balance is {available}. "
            "Add credits and try again."
        )


def available_balance(user):
    now = timezone.now()
    balance = user.credit_ledger_entries.aggregate(total=Sum("amount"))["total"] or 0
    reserved = CreditReservation.objects.filter(
        pipeline__order__customer=user,
        status=CreditReservation.Status.RESERVED,
    ).aggregate(total=Sum("credits"))["total"] or 0
    return balance - reserved


def analysis_credit_cost(duration_ms):
    return max(1, ceil(max(0, int(duration_ms)) / (30 * 60 * 1000)))


def clip_credit_cost(duration_ms):
    return max(1, ceil(max(0, int(duration_ms)) / 60_000))


def next_reservation_attempt(pipeline, kind):
    last = CreditReservation.objects.filter(pipeline=pipeline, kind=kind).order_by("-attempt").values_list("attempt", flat=True).first()
    return (last or 0) + 1


@transaction.atomic
def reserve_credits(pipeline, kind, attempt, credits, *, usage_items=None):
    credits = int(credits)
    if credits <= 0:
        return None

    user_model = get_user_model()
    user_model.objects.select_for_update().get(pk=pipeline.order.customer_id)
    existing = CreditReservation.objects.select_for_update().filter(
        pipeline=pipeline, kind=kind, attempt=attempt
    ).first()
    if existing:
        if existing.status == CreditReservation.Status.RESERVED:
            return existing
        if existing.status == CreditReservation.Status.CAPTURED:
            return existing
        raise ValueError("This credit reservation was already released. Retry the job to create a new attempt.")

    balance = CreditLedgerEntry.objects.filter(user_id=pipeline.order.customer_id).aggregate(
        total=Sum("amount")
    )["total"] or 0
    already_reserved = CreditReservation.objects.filter(
        pipeline__order__customer_id=pipeline.order.customer_id,
        status=CreditReservation.Status.RESERVED,
    ).aggregate(total=Sum("credits"))["total"] or 0
    available = balance - already_reserved
    if available < credits:
        raise InsufficientCredits(credits, available)

    return CreditReservation.objects.create(
        pipeline=pipeline,
        kind=kind,
        attempt=attempt,
        credits=credits,
        usage_items=usage_items or {},
    )


@transaction.atomic
def capture_reservation(reservation, *, charged_credits=None, description, actor=None):
    user_id = CreditReservation.objects.filter(pk=reservation.pk).values_list(
        "pipeline__order__customer_id", flat=True
    ).get()
    get_user_model().objects.select_for_update().get(pk=user_id)
    locked = CreditReservation.objects.select_for_update().select_related(
        "pipeline__order"
    ).get(pk=reservation.pk)
    if locked.status != CreditReservation.Status.RESERVED:
        return locked

    amount = locked.credits if charged_credits is None else int(charged_credits)
    amount = max(0, min(amount, locked.credits))
    if amount:
        CreditLedgerEntry.objects.create(
            user_id=locked.pipeline.order.customer_id,
            reservation=locked,
            entry_type=CreditLedgerEntry.Type.SPEND,
            amount=-amount,
            description=description[:180],
            created_by=actor,
        )
        locked.status = CreditReservation.Status.CAPTURED
        locked.charged_credits = amount
    else:
        locked.status = CreditReservation.Status.RELEASED
        locked.charged_credits = 0
    locked.settled_at = timezone.now()
    locked.save(update_fields=["status", "charged_credits", "settled_at"])
    return locked


@transaction.atomic
def release_reservation(reservation):
    locked = CreditReservation.objects.select_for_update().get(pk=reservation.pk)
    if locked.status == CreditReservation.Status.RESERVED:
        locked.status = CreditReservation.Status.RELEASED
        locked.charged_credits = 0
        locked.settled_at = timezone.now()
        locked.save(update_fields=["status", "charged_credits", "settled_at"])
    return locked


def render_usage_items(clips):
    return {
        str(clip.pk): clip_credit_cost(
            clip.end_ms - clip.start_ms - int(clip.editing_instructions.get("trim_start_ms", 0))
        )
        for clip in clips
    }


def reserve_render_credits(pipeline, clips, attempt):
    costs = render_usage_items(clips)
    return reserve_credits(
        pipeline,
        CreditReservation.Kind.RENDER,
        attempt,
        sum(costs.values()),
        usage_items={"clip_costs": costs},
    )


def settle_render_reservation(reservation):
    if reservation is None or reservation.status != CreditReservation.Status.RESERVED:
        return reservation
    from apps.processing.models import Clip

    costs = reservation.usage_items.get("clip_costs", {})
    rendered_ids = set(
        Clip.objects.filter(
            pk__in=[int(clip_id) for clip_id in costs],
            status=Clip.Status.RENDERED,
        ).values_list("pk", flat=True)
    )
    charged = sum(int(cost) for clip_id, cost in costs.items() if int(clip_id) in rendered_ids)
    title = reservation.pipeline.order.title
    if reservation.kind == CreditReservation.Kind.RENDER:
        description = f"Rendered clip exports for {title}"
    else:
        description = f"Source analysis for {title}"
    return capture_reservation(
        reservation,
        charged_credits=charged,
        description=description,
    )
