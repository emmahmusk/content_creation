from django.core.management.base import BaseCommand
from apps.orders.models import ContentOrder
from apps.processing.models import PipelineRun
from apps.processing.pipeline import execute_pipeline

class Command(BaseCommand):
    help="Process an order synchronously (useful without Redis during development)."
    def add_arguments(self,parser): parser.add_argument("order_id")
    def handle(self,*args,**options):
        order=ContentOrder.objects.get(pk=options["order_id"])
        run=PipelineRun.objects.create(order=order); execute_pipeline(run.id)
        self.stdout.write(self.style.SUCCESS(f"Pipeline {run.id} completed and awaits review."))
