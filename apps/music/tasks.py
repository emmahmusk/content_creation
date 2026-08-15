from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from django.conf import settings

from .services.pipeline import analyze_project, generate_project

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="afrofusion-studio")


@shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_kwargs={"max_retries": 2})
def analyze_music_project(self, project_id):
    analyze_project(project_id)


@shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_kwargs={"max_retries": 2})
def generate_music_project(self, project_id):
    generate_project(project_id)


def dispatch_analysis(project_id):
    if settings.PIPELINE_EXECUTION_MODE == "thread":
        return _executor.submit(analyze_project, str(project_id))
    return analyze_music_project.delay(str(project_id))


def dispatch_generation(project_id):
    if settings.PIPELINE_EXECUTION_MODE == "thread":
        return _executor.submit(generate_project, str(project_id))
    return generate_music_project.delay(str(project_id))
