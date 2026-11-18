from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.orders.models import SourceAsset
from apps.processing.services import cloudinary_media, source_handoff


class Command(BaseCommand):
    help = "Find abandoned Cloudinary originals older than 24 hours; add --delete to remove them."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true")

    def handle(self, *args, **options):
        if not cloudinary_media.configured():
            raise CommandError("Cloudinary is not configured.")
        cloudinary_media._configure()
        import cloudinary.api
        cutoff = timezone.now() - timedelta(hours=24)
        cursor = None
        found = 0
        while True:
            params = {"resource_type": "video", "type": "upload", "prefix": "recast/source/", "max_results": 100}
            if cursor:
                params["next_cursor"] = cursor
            try:
                result = cloudinary.api.resources(**params)
            except Exception:
                raise CommandError("Could not list source recordings. Check Cloudinary access and retry.") from None
            for resource in result.get("resources", []):
                public_id = resource.get("public_id", "")
                created = parse_datetime(resource.get("created_at", ""))
                if not public_id.startswith("recast/source/") or not created or timezone.is_naive(created) or created >= cutoff:
                    continue
                if SourceAsset.objects.filter(cloudinary_public_id=public_id).exists():
                    continue
                found += 1
                if options["delete"]:
                    source_handoff.remove_unreferenced_original(public_id)
            cursor = result.get("next_cursor")
            if not cursor:
                break
        self.stdout.write(f"Found {found} unclaimed originals older than 24 hours. " + ("Cleanup attempted; check logs for failures." if options["delete"] else "Dry run; add --delete to remove them."))
