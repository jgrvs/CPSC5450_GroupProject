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
