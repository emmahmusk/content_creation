from celery import shared_task
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from .pipeline import execute_pipeline

_local_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recast-poc")

@shared_task(bind=True,autoretry_for=(ConnectionError,TimeoutError),retry_backoff=True,retry_kwargs={"max_retries":3})
def process_order(self,run_id):
    execute_pipeline(run_id)

def dispatch_pipeline(run_id):
    """Dispatch locally for the POC or through Celery in a production worker setup."""
    if settings.PIPELINE_EXECUTION_MODE == "thread":
        return _local_executor.submit(execute_pipeline, str(run_id))
    return process_order.delay(str(run_id))
