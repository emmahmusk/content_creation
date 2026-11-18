# Kraftaa

A production-ready Django/DRF foundation for an AI-powered clipping production pipeline built for high-volume content teams. Agencies, professional clippers, creator teams, and growing operators submit one long-form recording, review AI-ranked moments with reasoning, and selectively produce publication-ready clip batches without spending render or generation budget on rejected ideas.

The content engine runs an end-to-end, resumable pipeline: media validation, 16 kHz audio extraction, timestamped speech recognition and clip discovery (Groq by default, with NVIDIA Riva/NIM available as an alternative), human approval/rejection, optional AI-planned B-roll, vertical H.264 renders with restrained captions, hooks, reframing, SRT files, source-derived thumbnails, social/YouTube/newsletter copy, optional cleaned audio, batch export, and quality-review handoff.

## Local setup

Use Python 3.13. Python 3.14 is not currently supported by the NVIDIA Riva client's pinned gRPC packages on Windows.

1. Create and activate your Python 3.13 virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and adjust its values (a local `.env` is already included for convenience).
4. Run `python manage.py migrate`.
5. Create staff access with `python manage.py createsuperuser`.
6. Start the service with `python manage.py runserver`.

The default local configuration uses `PIPELINE_EXECUTION_MODE=thread`, so processing buttons run jobs in a background thread inside the Django process. Redis and a Celery worker are not required locally; start only `python manage.py runserver`. FFmpeg and FFprobe are used for media processing. YouTube imports use current `yt-dlp` (2026.10.26 or newer) and are enabled by default. Set `YOUTUBE_IMPORTS_ENABLED=False` to disable them. Install Deno (2.3+) on PATH, or Node (22+) with `YOUTUBE_JS_RUNTIME=node`; the Docker image includes Node. The `yt-dlp[default]` dependency supplies the EJS scripts needed for current YouTube extraction.

For production, set `PIPELINE_EXECUTION_MODE=celery`, configure `CELERY_BROKER_URL` with a durable Redis-compatible broker, and run `celery -A config worker -l info`. Do not enable Celery mode without a running broker.

Alternatively, after filling in `.env`, run `docker compose up --build`; the included stack supplies PostgreSQL, Redis, FFmpeg, the Django web process, and a Celery media worker.

Open `http://127.0.0.1:8000/`. Staff manage orders and publish deliverables at `/admin/`; the browsable, versioned API is at `/api/v1/`.

## Architecture

- `accounts`: customer profile and registration.
- `orders`: order intake, source files/links, 24-hour deadline, and activity history.
- `deliverables`: versioned output packages and downloadable files.
- `processing`: resumable pipeline runs, individual stage attempts, timestamped transcripts, clip plans, renders, captions, and thumbnails.
- `music`: rights-safe reference analysis, original AfroFusion song direction, editable lyrics, structured production plans, and export assets.
- `core`: public pages and service health check.
- `config`: environment-led application configuration and API routing.

All customer web views and API querysets are tenant-scoped. Staff can see all orders, update production statuses through the API/admin, and create deliverables. SQLite is the local default; set a PostgreSQL `DATABASE_URL` for deployment. Supabase session-pooler URLs are supported, including URL-escaped credentials and SSL. Uploaded media uses local storage by default; the `STORAGES` setting is the extension point for S3-compatible storage. The app is WSGI/ASGI ready, serves compressed static assets with WhiteNoise, and exposes `/health/` for platform probes.

### Supabase PostgreSQL on Render

In the Render web service environment, set `DATABASE_URL` to the Supabase **Session pooler** connection URI (port `5432`) and replace `[YOUR-PASSWORD]` with the database password from Supabase. Keep this value in Render's secret environment settings; do not commit it or paste the real password into source files. If the password contains URI-reserved characters, URL-encode the password before inserting it into the URI. Supabase pooler hosts automatically use `sslmode=require`; `DB_SSLMODE` can override that setting and `DATABASE_CONN_MAX_AGE` controls Django's persistent connection lifetime. Then deploy and run `python manage.py migrate` once against the configured Supabase database. This creates/updates the schema; it does not copy existing SQLite user data.

## Approval-first production workflow

1. A team creates a production batch and uploads a file or provides an authorized public URL.
2. Kraftaa transcribes the source, discovers the strongest moments, and explains each recommendation.
3. A human approves or rejects moments before costly generation and rendering begins.
4. Approved clips optionally receive AI-selected stock, AI-generated, or hybrid B-roll at minimal, moderate, or aggressive frequency.
5. The finishing pipeline applies B-roll, captions, hooks, reframing, audio, and export polish.
6. The team reviews and downloads a complete publication-ready clip batch.

`No B-roll` is the default and preserves the established rendering path. B-roll planning runs only after approval and is fail-soft: if a stock or generation provider is unavailable, the approved clip still renders from its source footage. `AI-selected` uses licensed Pexels video when configured and can fall back to NVIDIA-generated visuals; `AI-generated` uses NVIDIA visual generation; `Stock + AI-generated` combines both.

## API

Session and Basic authentication are enabled initially. Endpoints include `/api/v1/orders/`, `/api/v1/assets/`, and `/api/v1/deliverables/`. Add token/JWT authentication at the REST framework boundary when a mobile client or external integration needs it.

Processing endpoints are `/api/v1/pipeline-runs/`, `/api/v1/clips/`, and `/api/v1/transcript/`. A failed or queued run can be dispatched with `POST /api/v1/pipeline-runs/{id}/retry/`.

Music Studio endpoints begin at `/api/v1/music-projects/`. Projects expose owner-scoped status and assets; the `direction`, `lyrics`, `progress`, and `retry` actions support the studio workflow without exposing another customer’s sessions.

## NVIDIA configuration

Add the provided key to `NVIDIA_API_KEY` in `.env`. Text generation uses the OpenAI-compatible NVIDIA NIM endpoint and its model is configurable with `NVIDIA_LLM_MODEL`. Transcription uses NVIDIA Riva gRPC; its server, function ID, and language are all environment settings. Optional generated B-roll uses `NVIDIA_IMAGE_API_URL`, `NVIDIA_IMAGE_MODEL`, `NVIDIA_VIDEO_API_URL`, and `NVIDIA_VIDEO_MODEL`; licensed stock discovery uses `PEXELS_API_KEY`. With no key, `PIPELINE_ALLOW_MOCK_AI=True` permits deterministic development output while still exercising the database workflow. Set it to `False` in production so missing credentials fail loudly. Never commit `.env`.

When `AI_PROVIDER=nvidia`, the default ASR is Parakeet TDT 0.6B v2, chosen for punctuation and word timestamps, and the default strategist is NVIDIA Nemotron Nano 9B v2. These model names and endpoint identifiers are configuration, not hard-coded workflow assumptions, so newer NIM endpoints can be swapped without migrations.

Install `requirements-nvidia.txt` instead of the base requirements only when using the NVIDIA/Riva provider. The Groq workflow uses the standard requirements and does not need the Riva gRPC packages.

## Groq clip-finder

The default configuration uses Groq for timestamped Whisper transcription and clip recommendations. Set `groq_api_key` in `.env` or Render; `GROQ_TEXT_MODEL` and `GROQ_TRANSCRIPTION_MODEL` can override the defaults. Groq response telemetry is written to the application logs (Render captures stdout/stderr), including endpoint, model, status, request ID, rate-limit remaining/limit/reset headers, retry-after, and the provider's structured error code/message. Prompts, transcripts, uploaded files, and API keys are never included. Use these fields to distinguish request-per-minute, token-per-minute, daily quota, and malformed-request errors; `GROQ_LOG_LEVEL` defaults to `INFO`. Long transcripts are reviewed in overlapping windows controlled by `GROQ_TRANSCRIPT_WINDOW_CHARS` (default 12000 characters), preserving the end of the recording and ranking non-overlapping candidates across windows. Short provider cooldowns of up to 60 seconds are respected; oversized requests are not retried unchanged. Analysis produces timestamped recommendations and instant previews; the customer approves the moments they want, then **Produce approved clips** creates vertical MP4 clips, matching MP3 audio cuts, movie-style SRT captions, thumbnails, and a downloadable ZIP without repeating transcription or ranking. Use `PIPELINE_EXECUTION_MODE=thread` locally or `celery` with a durable production worker. FFmpeg and FFprobe power final rendering and the local fallback path.

### Cloudinary-first media pipeline

Set the Cloudinary credentials and keep `MEDIA_PIPELINE_PRIMARY=cloudinary`. The source is uploaded once, Cloudinary supplies duration metadata and a compressed 16 kHz/64 kbps MP3 for timestamped STT, and AI-selected ranges receive lazy 9:16 preview URLs immediately. Approved ranges are rendered by FFmpeg for precise captions, thumbnails, audio, and downloadable files. If Cloudinary is unavailable, FFprobe and FFmpeg automatically provide ingest and audio extraction; if local media tools fail, `CLOUDINARY_FALLBACK_ENABLED=True` enables the reverse fallback. `SUBTITLE_FONT_SIZE` and `SUBTITLE_MARGIN_V` control movie-style captions and their lower-middle placement, while `SUBTITLE_MAX_WORDS` controls words displayed at once. These are separate settings; font size uses libass's compact subtitle scale rather than output pixels.

### Upload recordings before queuing work

With Cloudinary configured, the new-project page sends recording bytes directly from the browser to Cloudinary in signed chunks. It shows upload progress and cancellation, then submits only a short-lived upload token with the project brief. Cloudinary's API secret stays on the server. The server verifies the completed recording with Cloudinary, checks media type and size, binds it to the signed-in account, and prevents the same upload token being attached to another project. No unsigned upload preset is required.

The project and queued pipeline record are accepted only after storage verification succeeds. Actual processing still starts through the existing project action and credit checks. Failed or cancelled uploads do not queue processing. API clients can request a signature through authenticated `POST /orders/source-upload/` with JSON `filename`, `size`, and `rights_confirmed: true`, upload to the returned endpoint, and send the returned `token` as `cloudinary_upload_token` to `/api/v1/assets/`. They must wait for the final chunk response before submitting the token. Tokens expire after one hour; choose the recording again if the token expires. The server fetches trusted metadata itself and ignores client-supplied asset URLs/IDs.

Multipart API uploads, browsers without direct upload, and source-recovery uploads also store recordings in Cloudinary before creating or restarting work. These fallback transfers pass through the web service and are subject to its request timeouts, so direct browser uploads are preferred for large files. Dispatch guards transfer older local files before sending a Celery job, then delete their local copies after the database commit. A storage error prevents dispatch and keeps an existing source available for retry.

Configure these values on both the Render web service and Celery worker:

```text
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
CLOUDINARY_DIRECT_UPLOADS_ENABLED=True
MEDIA_PIPELINE_PRIMARY=cloudinary
```

Keep `PIPELINE_EXECUTION_MODE=celery` and the same `DATABASE_URL` and `CELERY_BROKER_URL` on both services. The broker receives job identifiers; the worker restores recordings from Cloudinary into its temporary work directory. Cloudinary stores the media and supplies existing transformations; Render still runs the website, worker and FFmpeg production. Cloudinary credentials are mandatory for uploaded-file dispatch in Celery mode. Local thread mode can retain its file-only development fallback when credentials are absent. Upload size must fit both `PUBLIC_MEDIA_MAX_BYTES` and the Cloudinary account's own limits.

Run `python manage.py collectstatic --noinput` and restart web/worker processes when deploying this update. No additional database migration is introduced by the handoff itself. Use `python manage.py cleanup_unclaimed_sources` for a dry run listing the count of abandoned originals older than 24 hours; add `--delete` to remove them. It only considers the app's `recast/source/` originals without a SourceAsset reference, preserving current projects, recent uploads and clip exports. This also covers completed uploads abandoned before project submission. Run this maintenance command regularly on the worker host. Existing YouTube source cleanup and uploaded-original retention remain in place.

Verification: `python manage.py test apps.orders.test_source_handoff` exercises ownership, replay protection, failure handling, API/browser intake and handoff to an empty worker disk. `node --test tests/source-upload.test.cjs` checks browser chunking, form submission, retry and cancellation. Primary reference: [Cloudinary signed and chunked uploads](https://cloudinary.com/documentation/upload_images).

### YouTube URL imports, AI briefs and source cleanup

On the new-project page, paste one YouTube video URL, confirm content rights and click **Suggest with AI** next to the source. This drafts the title, audience/project brief, worthwhile moments, exclusions and brand voice from the public title and description, without claiming to have transcribed the recording. Existing text stays in place unless the user selects **Replace text already entered**. File names and manually entered topics are also supported. The user reviews the draft before creating the project; transcription and clip analysis happen in the normal pipeline, and production still respects the approval/credit gates.

`YOUTUBE_IMPORTS_ENABLED=True` enables URL intake and real imports. The operator command below contacts YouTube for one video's metadata, but does not download media, create orders, reserve credits, run AI, render clips, or publish anything. Substitute a real video URL that you own or have permission to download. This is a network preflight, not proof that the media download will succeed.

```powershell
python manage.py check_youtube_import "https://www.youtube.com/watch?v=VIDEO_ID" --rights-confirmed
```

Live imports require FFmpeg/FFprobe, the JavaScript runtime described above, and `YOUTUBE_IMPORTS_ENABLED=True` in your environment. Restart Django and workers after changing configuration. First download one authorized source into an isolated test directory:

```powershell
python manage.py check_youtube_import "https://www.youtube.com/watch?v=VIDEO_ID" --rights-confirmed --download --output-dir tmp/youtube-test
```

That command downloads real media without running the production pipeline. Then create a test project with the same URL and rights confirmation to exercise ingestion and analysis. AI mock settings are independent of YouTube testing. Customer web forms, the API, model validation and the pipeline reject YouTube URL imports while the live switch is off. Uploads and direct media imports remain available.

The importer accepts one video per job, caps video selection at 1080p, checks combined download bytes against `PUBLIC_MEDIA_MAX_BYTES`, and rejects playlists, channels, live streams and upcoming streams. Temporary media and copied cookie files are removed on success, failure or cancellation. Abrupt process termination can leave temporary files for operator cleanup. Downloaded originals use an internal `SourceAsset.imported_file` cache, separate from user uploads. The cache survives the analysis/approval handoff, preventing a second download just to render approved moments. On successful export, the local imported original and any Cloudinary source copy and derived preview URLs are removed; rendered MP4/MP3/SRT/thumbnail exports remain. The same cleanup runs after a successful automatic pipeline and on cancellation. Downloaded originals are not removed at the analysis-only review step. Later requests for more clips, reanalysis or restored exports can reimport the URL; YouTube must still permit access. Uploaded originals keep their existing retention behavior. Failed jobs retain their managed source for retry, while their temporary work files are removed.

Requests use randomized 10-25 second download delays and at least 1.5 seconds between extractor requests. Retries are disabled. A file lock serializes imports across processes sharing `MEDIA_ROOT`; request spacing and a six-hour cooldown after 429, bot-check or 403 errors persist there across restarts. Short request-spacing intervals are waited out; requests during a block cooldown fail with upload/retry guidance. Brief metadata is cached for five minutes to reduce repeated extraction. The app does not automatically retry these jobs or rotate IP addresses. A separate container or host with independent storage has an independent lock: use one import worker or shared storage across all import workers before production rollout.

Optional configuration:

- `YOUTUBE_PROXY_URL`: a fixed operator-managed HTTP or SOCKS5 endpoint. Keep credentials in environment secrets. Empty means a direct connection. A system VPN requires no application change.
- `YOUTUBE_MAX_HEIGHT`: source video height cap (144-1080, default 1080). Lower values can reduce development download size.
- `YOUTUBE_IP_FAMILY`: `auto`, `4` or `6` for network compatibility. This maps to yt-dlp's `source_address`; it does not rotate addresses after blocks.
- `YOUTUBE_SLEEP_MIN`, `YOUTUBE_SLEEP_MAX`, `YOUTUBE_SLEEP_REQUESTS`: conservative throttling settings, with enforced minimums of 10, 10 and 1.5 seconds respectively.
- `YOUTUBE_BLOCK_COOLDOWN_SECONDS`: minimum 3600 seconds; defaults to 21600.
- `YOUTUBE_COOKIE_FILE` (Netscape format) or `YOUTUBE_COOKIES_BROWSER` plus optional `YOUTUBE_BROWSER_PROFILE`: an operator-controlled session for an authorized local test. Select one source, then explicitly add `--use-auth` to the test command. Browser extraction requires access to that browser/profile and may fail on locked or encrypted cookie stores. The original cookie file is copied into temporary storage, not modified. Cookies are never used by customer pipeline jobs and are never returned to the browser. Do not use a shared account to supply access to other customers' content.

Provider diagnostics are suppressed so signed URLs, proxy credentials and session details are not stored in project errors. A blocked request returns upload-and-retry recovery guidance. These packages cannot guarantee access or remove video permissions, geography restrictions or YouTube rate limits. Use the original recording or YouTube Studio export when an import is denied. OAuth device verification is not implemented; the previous README description was stale.

Current upstream references: [embedding/options](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp), [YouTube extractor guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube), and [JavaScript runtime/EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Run `python manage.py migrate` before starting the updated app; this adds internal source retention fields. Install the updated requirements, run `python manage.py collectstatic --noinput`, and restart web/worker processes when deploying.

Use `python manage.py cleanup_youtube_sources --older-than-hours 24` to remove abandoned review sources and retry failed remote deletions. Active jobs are skipped. Run this maintenance command regularly on the worker host. Abrupt process termination can also leave temporary job files for operator cleanup.

Run isolated adapter/workflow checks with `python manage.py test apps.processing.test_youtube apps.processing.test_youtube_workflow` (no YouTube or AI requests). Broader regression checks use `python manage.py test apps.processing apps.orders` against Django's test database.

## Content Intelligence

Every suggestion in the Publishing Queue opens a dedicated Content Intelligence Review. The review is generated asynchronously from the timestamped transcript, AI Mission, audience definition, brand voice, and selected platforms. It stores versioned Content DNA, editorial reasoning, platform strategies, business predictions, audience matching, semantic relationships, AI editor recommendations, and ten editable repurposing assets. Without an AI key the same complete workflow uses an evidence-based deterministic baseline, which keeps local development and tests functional.

Saved social handles are intentionally treated as destinations rather than authenticated accounts. Users can create drafts, queues, and schedules for those destinations. Direct publish and republish requests are rejected until a platform OAuth connector is present, avoiding a misleading “connected” state or unsafe token storage. `PublicationJob` and `LearningSignal` provide the stable adapter and feedback boundaries for authenticated connectors and performance ingestion.

## AI AfroFusion Studio

Authenticated creators can open `/music/` as a separate workspace from clipping. The upload gate accepts MP3, WAV, FLAC, AAC, and M4A up to 150 MB and requires both rights and analysis-only confirmations. FFprobe and FFmpeg extract technical metadata and a lightweight energy/tempo profile; Groq turns those high-level measurements into a producer report and, after the creator supplies direction, generates an original concept, lyrics, arrangement, chord map, and melody plan.

The reference is never transcribed for lyrics, separated into stems, sampled, or used for artist/voice imitation. The current feature exports editable lyrics and structured project JSON. Melody audio, beat generation, licensed vocal synthesis, and mix/master rendering are intentionally presented as provider adapter slots rather than simulated completed outputs. With no Groq key, `PIPELINE_ALLOW_MOCK_AI=True` keeps the workflow available using deterministic original development content; disable that fallback in production.

## Deployment checklist

Set `DEBUG=False`, use a strong `SECRET_KEY`, configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, PostgreSQL, durable media storage, transactional email, HTTPS, backups, and worker/queue infrastructure before automating transcription or media processing. Run `python manage.py collectstatic` and serve with `gunicorn config.wsgi:application`.
