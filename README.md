# Recast

A production-ready Django/DRF foundation for a 24-hour content repurposing service. Customers submit a long-form recording and receive clip ideas, hooks and captions, social posts, a YouTube package, long-form writing, and optionally cleaned audio.

The content engine now runs an end-to-end, resumable pipeline: media validation, 16 kHz audio extraction, NVIDIA speech recognition with word timestamps, NVIDIA NIM content strategy, ten vertical H.264 renders with burned-in captions, SRT files, source-derived thumbnails, social/YouTube/newsletter copy, optional cleaned audio, and quality-review handoff.

## Local setup

Use Python 3.13. Python 3.14 is not currently supported by the NVIDIA Riva client's pinned gRPC packages on Windows.

1. Create and activate your Python 3.13 virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and adjust its values (a local `.env` is already included for convenience).
4. Run `python manage.py migrate`.
5. Create staff access with `python manage.py createsuperuser`.
6. Start the service with `python manage.py runserver`.

For background processing, install FFmpeg (both `ffmpeg` and `ffprobe` must be on `PATH`), start Redis, then run `celery -A config worker -l info` in a separate terminal. For development without Redis, process an order synchronously with `python manage.py process_order ORDER_UUID`.

Alternatively, after filling in `.env`, run `docker compose up --build`; the included stack supplies PostgreSQL, Redis, FFmpeg, the Django web process, and a Celery media worker.

Open `http://127.0.0.1:8000/`. Staff manage orders and publish deliverables at `/admin/`; the browsable, versioned API is at `/api/v1/`.

## Architecture

- `accounts`: customer profile and registration.
- `orders`: order intake, source files/links, 24-hour deadline, and activity history.
- `deliverables`: versioned output packages and downloadable files.
- `processing`: resumable pipeline runs, individual stage attempts, timestamped transcripts, clip plans, renders, captions, and thumbnails.
- `core`: public pages and service health check.
- `config`: environment-led application configuration and API routing.

All customer web views and API querysets are tenant-scoped. Staff can see all orders, update production statuses through the API/admin, and create deliverables. SQLite is the local default; set a PostgreSQL `DATABASE_URL` for deployment. Uploaded media uses local storage by default; the `STORAGES` setting is the extension point for S3-compatible storage. The app is WSGI/ASGI ready, serves compressed static assets with WhiteNoise, and exposes `/health/` for platform probes.

## Typical production workflow

1. Customer creates an order and attaches a file or private URL.
2. Staff reviews the source and advances its status.
3. Staff adds each output as a `Deliverable`, using text or a file.
4. Staff marks deliverables ready and the order delivered.
5. Customer sees and downloads/copies completed assets from their dashboard.

## API

Session and Basic authentication are enabled initially. Endpoints include `/api/v1/orders/`, `/api/v1/assets/`, and `/api/v1/deliverables/`. Add token/JWT authentication at the REST framework boundary when a mobile client or external integration needs it.

Processing endpoints are `/api/v1/pipeline-runs/`, `/api/v1/clips/`, and `/api/v1/transcript/`. A failed or queued run can be dispatched with `POST /api/v1/pipeline-runs/{id}/retry/`.

## NVIDIA configuration

Add the provided key to `NVIDIA_API_KEY` in `.env`. Text generation uses the OpenAI-compatible NVIDIA NIM endpoint and its model is configurable with `NVIDIA_LLM_MODEL`. Transcription uses NVIDIA Riva gRPC; its server, function ID, and language are all environment settings. With no key, `PIPELINE_ALLOW_MOCK_AI=True` permits deterministic development output while still exercising the database workflow. Set it to `False` in production so missing credentials fail loudly. Never commit `.env`.

The default ASR is Parakeet TDT 0.6B v2, chosen for punctuation and word timestamps. The default strategist is NVIDIA Nemotron Nano 9B v2. These model names and endpoint identifiers are configuration, not hard-coded workflow assumptions, so newer free NIM endpoints can be swapped without migrations.

## Deployment checklist

Set `DEBUG=False`, use a strong `SECRET_KEY`, configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, PostgreSQL, durable media storage, transactional email, HTTPS, backups, and worker/queue infrastructure before automating transcription or media processing. Run `python manage.py collectstatic` and serve with `gunicorn config.wsgi:application`.
