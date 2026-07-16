from celery import shared_task
from .pipeline import execute_pipeline

@shared_task(bind=True,autoretry_for=(ConnectionError,TimeoutError),retry_backoff=True,retry_kwargs={"max_retries":3})
def process_order(self,run_id):
    execute_pipeline(run_id)
