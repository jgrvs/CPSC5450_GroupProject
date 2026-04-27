from __future__ import annotations

import uuid
from uuid import UUID
from typing import Any, Optional

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models.user import Item, ItemCreate, User, UserCreate, UserUpdate
from app.models.email import EmailEvent, EmailParsed, EmailStatus

from datetime import datetime, timezone

def coerce_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Handles "2026-02-27T..." and "2026-02-27T...Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None

def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


def create_item(*, session: Session, item_in: ItemCreate, owner_id: uuid.UUID) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_email_event(
        session: Session,
        *,
        event_id: UUID,
        source_filename: str,
        raw_path: str,
    ) -> EmailEvent:
    row = EmailEvent(
        event_id=event_id,
        source_filename=source_filename,
        raw_path=raw_path,
        status=EmailStatus.queued,
        error=None,
        processed_at=None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_email_event_status(
    session: Session,
    *,
    event_id: UUID,
    status: EmailStatus,
    error: Optional[str] = None,
    processed_at: Optional[datetime] = None,
    raw_path: Optional[str] = None,
) -> None:
    row = session.get(EmailEvent, event_id)
    if row is None:
        return
    row.status = status
    row.error = error
    if raw_path is not None:
        row.raw_path = raw_path
    if processed_at is not None:
        row.processed_at = processed_at
    if processed_at is None and status in (EmailStatus.done, EmailStatus.failed):
        processed_at = utcnow()
    if processed_at is not None:
        row.processed_at = processed_at
    session.commit()


def find_by_canonical_fingerprint(session: Session, canonical_fingerprint: str) -> EmailParsed | None:
    statement = select(EmailParsed).where(EmailParsed.canonical_fingerprint == canonical_fingerprint)
    return session.exec(statement).first()


def reconcile_duplicates(session: Session, canonical_fingerprint: str) -> None:
    """Ensure exactly one root and all others point to it.

    Run after every upsert to fix races where concurrent workers all inserted
    with duplicate_of=None before seeing each other's committed rows.
    Root is chosen deterministically by lowest event_id UUID value.
    """
    rows = session.exec(
        select(EmailParsed)
        .where(EmailParsed.canonical_fingerprint == canonical_fingerprint)
        .order_by(EmailParsed.event_id)
    ).all()

    if len(rows) <= 1:
        return

    root_id = rows[0].event_id
    for row in rows:
        if row.event_id == root_id:
            if row.duplicate_of is not None:
                row.duplicate_of = None
                session.add(row)
        else:
            if row.duplicate_of != root_id:
                row.duplicate_of = root_id
                session.add(row)

    session.commit()


def upsert_email_parsed(
    session: Session,
    *,
    event_id: UUID,
    payload: dict,
    duplicate_of: Optional[UUID] = None,
) -> None:
    existing = session.get(EmailParsed, event_id)

    headers = payload.get("headers", {}) or {}
    auth = (headers.get("auth_results", {}) or {})
    flags = payload.get("derived_flags", {}) or {}
    kw = payload.get("keyword_counts", {}) or {}

    dt = coerce_dt(headers.get("date"))
    fp = payload.get("fingerprint")
    if not fp:
        raise ValueError("parsed payload missing fingerprint")
    cfp = payload.get("canonical_fingerprint")

    if existing is None:
        row = EmailParsed(
            event_id=event_id,
            fingerprint=fp,
            canonical_fingerprint=cfp,
            duplicate_of=duplicate_of,
            from_address=headers.get("from_address"),
            to_address=headers.get("to_address"),
            subject=headers.get("subject"),
            date=dt,
            spf=auth.get("spf"),
            dkim=auth.get("dkim"),
            dmarc=auth.get("dmarc"),
            display_name_mismatch=bool(flags.get("display_name_mismatch", False)),
            sender_domain_mismatch=bool(flags.get("sender_domain_mismatch", False)),
            lookalike_domain_detected=bool(flags.get("lookalike_domain_detected", False)),
            internal_impersonation=bool(flags.get("internal_impersonation", False)),
            unicode_trick_detected=bool(flags.get("unicode_trick_detected", False)),
            urgency=kw.get("urgency"),
            credentials=kw.get("credentials"),
            payment=kw.get("payment"),
            threat=kw.get("threat"),
            prob_phishing=payload.get("p_phishing"),
            prob_benign=payload.get("p_benign"),
            parsed_payload=payload,
        )
        session.add(row)
    else:
        # if reprocessed, overwrite fields
        existing.fingerprint = fp
        existing.canonical_fingerprint = cfp
        existing.duplicate_of = duplicate_of
        existing.from_address = headers.get("from_address")
        existing.to_address = headers.get("to_address")
        existing.subject = headers.get("subject")
        existing.date = dt
        existing.spf = auth.get("spf")
        existing.dkim = auth.get("dkim")
        existing.dmarc = auth.get("dmarc")
        existing.display_name_mismatch = bool(flags.get("display_name_mismatch", False))
        existing.sender_domain_mismatch = bool(flags.get("sender_domain_mismatch", False))
        existing.lookalike_domain_detected = bool(flags.get("lookalike_domain_detected", False))
        existing.internal_impersonation = bool(flags.get("internal_impersonation", False))
        existing.unicode_trick_detected = bool(flags.get("unicode_trick_detected", False))
        existing.urgency = kw.get("urgency")
        existing.credentials = kw.get("credentials")
        existing.payment = kw.get("payment")
        existing.threat = kw.get("threat")
        existing.prob_phishing = payload.get("p_phishing")
        existing.prob_benign = payload.get("p_benign")
        existing.parsed_payload = payload
        session.add(existing)

    session.commit()
