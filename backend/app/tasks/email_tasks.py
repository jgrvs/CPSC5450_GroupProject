from __future__ import annotations

import logging
import time
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app import crud
from app.core.db import engine
from app.models.email import EmailStatus
from app.services.email_filesystem import (
    archive_raw_success,
    read_processing_eml,
    write_error,
    write_parsed_json,
)
from app.services.email_processing import parse_and_validate
from app.services.triage import TriageEngine
from app.tasks.worker import app

logger = logging.getLogger(__name__)

triage_engine = TriageEngine()


@app.task(bind=True, name="app.tasks.email_tasks.parse_inbox_email")
def parse_inbox_email(self, event_id: str, processing_path: str) -> dict:
    event_uuid = UUID(event_id)

    with Session(engine) as session:
        try:
            crud.set_email_event_status(session, event_id=event_uuid, status=EmailStatus.processing)

            eml_bytes = read_processing_eml(Path(processing_path))

            t0 = time.perf_counter()
            payload = parse_and_validate(eml_bytes, email_id=event_id)
            t1 = time.perf_counter()

            verdict = triage_engine.triage(payload)
            payload |= verdict
            t2 = time.perf_counter()

            out_path = write_parsed_json(event_id, payload)

            canonical_fp = payload.get("canonical_fingerprint")

            # Best-effort pre-check (may miss concurrent emails — reconcile fixes that)
            duplicate_of = None
            if canonical_fp:
                existing = crud.find_by_canonical_fingerprint(session, canonical_fp)
                if existing and existing.event_id != event_uuid:
                    duplicate_of = existing.event_id

            crud.upsert_email_parsed(session, event_id=event_uuid, payload=payload, duplicate_of=duplicate_of)

            # Fix any races: whichever task runs last will correct all duplicate_of values
            if canonical_fp:
                crud.reconcile_duplicates(session, canonical_fp)
            t3 = time.perf_counter()

            done_path = archive_raw_success(Path(processing_path))
            crud.set_email_event_status(session, event_id=event_uuid, status=EmailStatus.done, raw_path=str(done_path))

            logger.info(
                "email %s: parse=%.0fms triage=%.0fms db=%.0fms total=%.0fms",
                event_id,
                (t1 - t0) * 1000,
                (t2 - t1) * 1000,
                (t3 - t2) * 1000,
                (t3 - t0) * 1000,
            )

            return {"event_id": event_id, "parsed_path": str(out_path)}

        except Exception as e:
            write_error(event_id, f"Unhandled error: {e}")
            crud.set_email_event_status(session, event_id=event_uuid, status=EmailStatus.failed, error=str(e))
            raise
