from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.orders.models import SourceAsset
from apps.processing.services.youtube_sources import discard


class Command(BaseCommand):
    help = "Remove expired managed YouTube originals, including abandoned reviews; preserve uploads and clips."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-hours", type=int, default=24)

    def handle(self, *args, **options):
        hours = options["older_than_hours"]
        if hours < 1:
            raise CommandError("--older-than-hours must be at least 1.")
        removed = pending = 0
        for asset in SourceAsset.objects.filter(youtube_imported_at__lt=timezone.now() - timedelta(hours=hours)).select_related("order"):
            if discard(asset):
                removed += 1
            else:
                pending += 1
        self.stdout.write(f"Cleaned {removed} YouTube sources; {pending} active or awaiting cleanup retry.")
