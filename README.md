# CPSC5450_GroupProject
CPSC 5450 Group Project

## Getting Started

**Prerequisites:** Docker and Docker Compose must be installed.

**Start everything** (from the project root):

```bash
docker compose up --build
```

The `--build` flag is only needed the first time or after dependency changes. After that:

```bash
docker compose up
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | React/TanStack UI |
| Backend API | http://localhost:8000 | FastAPI |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Mailpit | http://localhost:8025 | Email testing UI |
| Pgweb | http://localhost:8081 | Postgres browser |
| RedisInsight | http://localhost:5540 | Redis GUI |

## Email Ingestion

Drop a `.eml` file into `backend/app/email_data/` to have it picked up by the parsing pipeline. This directory is mounted into both the backend and worker containers.

## Default Superuser Credentials

When the application starts for the first time, a superuser account is seeded automatically using the values in `backend/app/core/config.py` (or overridden by a `.env` file):

| Field    | Default value       |
|----------|---------------------|
| Email    | admin@example.com   |
| Password | admin12345          |

These credentials can be used to log in and test superuser-level access. Override them by setting `FIRST_SUPERUSER_EMAIL`, `FIRST_SUPERUSER_PASSWORD`, and `FIRST_SUPERUSER_FULL_NAME` in a `.env` file before starting the application.

## Stopping

```bash
docker compose down
```

Add `-v` to also wipe the database volumes for a clean slate:

```bash
docker compose down -v
```

## My contributions

Group project for CPSC 5450: an email triage system that ingests `.eml` files, parses them, scores phishing likelihood, and gives analysts a queue to review. Stack: FastAPI, Celery + Redis, Postgres, React (TanStack), Docker Compose. I worked on the backend pipeline and several analyst-facing features:

- **Email parser and schema.** Wrote the initial parser, then reworked the JSON schema and parser to handle nullable fields and better URL extraction.
- **API/parser separation.** Split routing from parsing logic. Routes are now thin, and the parser lives in a `services/` module.
- **Async ingestion pipeline.** Moved parsing into Celery tasks, with an orchestration module, a storage module for DB access, filesystem-backed email storage, job status tracking, and an `/ingest/inbox` endpoint that triggers processing.
- **Ingest improvements.** Per-file error handling, a Process Emails button on the dashboard, draining the full inbox with queue auto-refresh, a processing indicator, a 500-email synthetic test set, and purge endpoints for test resets.
- **Role-based access control.** Three-tier role hierarchy (viewer / analyst / superuser), a user management page, viewer access restrictions, a raw-email modal for privileged roles, and a seeded default superuser.
- **Campaign detection.** Canonical fingerprint deduplication so related phishing emails group into campaigns.
- **Analyst UI.** Surfaced the model's phishing probability in the UI, added click-to-expand cards for indicators, flags and rationale, and saved analyst resolutions to the database. *(In progress on a feature branch; not yet merged to `main`.)*
