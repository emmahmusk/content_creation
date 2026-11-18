import json
from tempfile import TemporaryDirectory
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.processing.services.youtube import import_video
from apps.processing.services.public_media import PublicMediaError


class Command(BaseCommand):
    help = "Test one authorized YouTube URL. Default: metadata only, no media or pipeline work."

    def add_arguments(self, parser):
        parser.add_argument("url")
        parser.add_argument("--rights-confirmed", action="store_true")
        parser.add_argument("--download", action="store_true", help="Download media; requires YOUTUBE_IMPORTS_ENABLED=True.")
        parser.add_argument("--output-dir", help="Required with --download.")
        parser.add_argument("--use-auth", action="store_true", help="Use the configured operator cookie source for this test only.")

    def handle(self, *args, **options):
        if not options["rights_confirmed"]:
            raise CommandError("Pass --rights-confirmed for content you own or are authorized to download.")
        if options["download"] and not options["output_dir"]:
            raise CommandError("--download requires --output-dir.")
        try:
            with TemporaryDirectory(prefix="youtube-check-") as temporary:
                result = import_video(
                    options["url"], Path(options["output_dir"]) if options["download"] else Path(temporary),
                    simulate=not options["download"], use_auth=options["use_auth"],
                )
            self.stdout.write(json.dumps(result) if isinstance(result, dict) else str(result))
        except (PublicMediaError, OSError, ValueError) as exc:
            if isinstance(exc, PublicMediaError):
                raise CommandError(str(exc)) from None
            raise CommandError("YouTube check failed. Check the runtime, network, proxy, cookie source and output permissions.") from None
