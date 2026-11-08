from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import ContentOrder, OrderEvent
from apps.processing.models import PipelineRun, StageRun


class PipelineCancelled(Exception):
    """Raised inside a worker when the customer has stopped the current run."""


def assert_pipeline_active(run):
    """Prevent an old worker from writing after a run has been cancelled."""
    status = PipelineRun.objects.filter(pk=run.pk).values_list("status", flat=True).get()
    if status == PipelineRun.Status.CANCELLED:
        run.status = status
        raise PipelineCancelled("Analysis stopped by the customer.")


@transaction.atomic
def cancel_pipeline_run(run, *, actor=None, reason="Project settings need to be edited."):
    """Persist cancellation first; workers observe it at their next safe checkpoint."""
    locked = PipelineRun.objects.select_for_update().select_related("order").get(pk=run.pk)
    if locked.status not in {PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING}:
        return locked, False

    now = timezone.now()
    locked.status = PipelineRun.Status.CANCELLED
    locked.current_stage = "cancelled_for_edit"
    locked.error = ""
    locked.finished_at = now
    locked.youtube_auth_url = ""
    locked.youtube_auth_code = ""
    locked.youtube_auth_confirmed = False
    locked.save(update_fields=["status", "current_stage", "error", "finished_at", "youtube_auth_url", "youtube_auth_code", "youtube_auth_confirmed", "updated_at"])
    locked.stages.filter(status=StageRun.Status.RUNNING).update(
        status=StageRun.Status.SKIPPED,
        error="",
        finished_at=now,
        metadata={"reason": reason},
    )

    order = locked.order
    order.status = ContentOrder.Status.REVISION
    order.save(update_fields=["status", "updated_at"])
    OrderEvent.objects.create(
        order=order,
        actor=actor,
        event_type="analysis_stopped",
        message="Analysis was stopped so the project brief could be edited.",
    )

    if settings.PIPELINE_EXECUTION_MODE == "celery":
        transaction.on_commit(lambda: _revoke_celery_task(locked.id))
    return locked, True


def _revoke_celery_task(run_id):
    try:
        current_app.control.revoke(str(run_id), terminate=False)
    except Exception:
        # The persisted cancelled state remains authoritative if the broker is unavailable.
        pass
