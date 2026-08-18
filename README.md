# Reeckast

A production-ready Django/DRF foundation for an AI-powered clipping production pipeline built for high-volume content teams. Agencies, professional clippers, creator teams, and growing operators submit one long-form recording, review AI-ranked moments with reasoning, and selectively produce publication-ready clip batches without spending render or generation budget on rejected ideas.

The content engine runs an end-to-end, resumable pipeline: media validation, 16 kHz audio extraction, NVIDIA speech recognition with word timestamps, NVIDIA NIM clip discovery and reasoning, human approval/rejection, optional AI-planned B-roll, vertical H.264 renders with restrained captions, hooks, reframing, SRT files, source-derived thumbnails, social/YouTube/newsletter copy, optional cleaned audio, batch export, and quality-review handoff.

## Local setup

Use Python 3.13. Python 3.14 is not currently supported by the NVIDIA Riva client's pinned gRPC packages on Windows.

1. Create and activate your Python 3.13 virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and adjust its values (a local `.env` is already included for convenience).
4. Run `python manage.py migrate`.
5. Create staff access with `python manage.py createsuperuser`.
6. Start the service with `python manage.py runserver`.

The default local configuration uses `PIPELINE_EXECUTION_MODE=thread`, so processing buttons run jobs in a background thread inside the Django process. Redis and a Celery worker are not required locally; start only `python manage.py runserver`. FFmpeg and Deno are still required for media and YouTube imports. Set `YTDLP_JS_RUNTIME` to the full Deno executable path when it is not available on `PATH`.

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

All customer web views and API querysets are tenant-scoped. Staff can see all orders, update production statuses through the API/admin, and create deliverables. SQLite is the local default; set a PostgreSQL `DATABASE_URL` for deployment. Uploaded media uses local storage by default; the `STORAGES` setting is the extension point for S3-compatible storage. The app is WSGI/ASGI ready, serves compressed static assets with WhiteNoise, and exposes `/health/` for platform probes.

## Approval-first production workflow

1. A team creates a production batch and uploads a file or provides an authorized public URL.
2. Reeckast transcribes the source, discovers the strongest moments, and explains each recommendation.
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

The default ASR is Parakeet TDT 0.6B v2, chosen for punctuation and word timestamps. The default strategist is NVIDIA Nemotron Nano 9B v2. These model names and endpoint identifiers are configuration, not hard-coded workflow assumptions, so newer free NIM endpoints can be swapped without migrations.

Install `requirements-nvidia.txt` instead of the base requirements only when using the NVIDIA/Riva provider. The OpenAI proof of concept does not require the Riva gRPC packages.

## OpenAI clip-finder proof of concept

The default configuration runs the OpenAI clipping workflow in two phases. Analysis produces timestamped recommendations and instant previews; the customer approves the moments they want, then **Produce approved clips** creates vertical MP4 clips, matching MP3 audio cuts, movie-style SRT captions, thumbnails, and a downloadable ZIP without repeating transcription or ranking. Use `PIPELINE_EXECUTION_MODE=thread` locally or `celery` with a durable production worker. FFmpeg and FFprobe power final rendering and the local fallback path.

### Cloudinary-first media pipeline

Set the Cloudinary credentials and keep `MEDIA_PIPELINE_PRIMARY=cloudinary`. The source is uploaded once, Cloudinary supplies duration metadata and a compressed 16 kHz/64 kbps MP3 for timestamped STT, and AI-selected ranges receive lazy 9:16 preview URLs immediately. Approved ranges are rendered by FFmpeg for precise captions, thumbnails, audio, and downloadable files. If Cloudinary is unavailable, FFprobe and FFmpeg automatically provide ingest and audio extraction; if local media tools fail, `CLOUDINARY_FALLBACK_ENABLED=True` enables the reverse fallback. `SUBTITLE_FONT_SIZE` and `SUBTITLE_MARGIN_V` control the restrained movie-subtitle appearance.

Public YouTube and other supported video-page URLs are imported with `yt-dlp`; direct media URLs continue through the lightweight HTTP downloader. Imports are limited to one video, capped at 1080p and `PUBLIC_MEDIA_MAX_BYTES`, and require the customer to confirm they own the content or have permission to download, clip, and republish it. Keep `yt-dlp` current because hosted-video extractors change regularly. The production image includes Deno and the yt-dlp EJS scripts required for current YouTube JavaScript challenges.

## Content Intelligence

Every suggestion in the Publishing Queue opens a dedicated Content Intelligence Review. The review is generated asynchronously from the timestamped transcript, AI Mission, audience definition, brand voice, and selected platforms. It stores versioned Content DNA, editorial reasoning, platform strategies, business predictions, audience matching, semantic relationships, AI editor recommendations, and ten editable repurposing assets. Without an AI key the same complete workflow uses an evidence-based deterministic baseline, which keeps local development and tests functional.

Saved social handles are intentionally treated as destinations rather than authenticated accounts. Users can create drafts, queues, and schedules for those destinations. Direct publish and republish requests are rejected until a platform OAuth connector is present, avoiding a misleading “connected” state or unsafe token storage. `PublicationJob` and `LearningSignal` provide the stable adapter and feedback boundaries for authenticated connectors and performance ingestion.

## AI AfroFusion Studio

Authenticated creators can open `/music/` as a separate workspace from clipping. The upload gate accepts MP3, WAV, FLAC, AAC, and M4A up to 150 MB and requires both rights and analysis-only confirmations. FFprobe and FFmpeg extract technical metadata and a lightweight energy/tempo profile; OpenAI turns those high-level measurements into a producer report and, after the creator supplies direction, generates an original concept, lyrics, arrangement, chord map, and melody plan.

The reference is never transcribed for lyrics, separated into stems, sampled, or used for artist/voice imitation. The current feature exports editable lyrics and structured project JSON. Melody audio, beat generation, licensed vocal synthesis, and mix/master rendering are intentionally presented as provider adapter slots rather than simulated completed outputs. With no OpenAI key, `PIPELINE_ALLOW_MOCK_AI=True` keeps the workflow testable using deterministic original development content; disable that fallback in production.

## Deployment checklist

Set `DEBUG=False`, use a strong `SECRET_KEY`, configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, PostgreSQL, durable media storage, transactional email, HTTPS, backups, and worker/queue infrastructure before automating transcription or media processing. Run `python manage.py collectstatic` and serve with `gunicorn config.wsgi:application`.
