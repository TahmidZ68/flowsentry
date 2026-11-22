from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import decrypt_json, encrypt_json, mask_secret
from app.core.ssrf import SSRFValidationError, build_ssrf_safe_transport, validate_outbound_url
from app.models.incidents import Incident
from app.models.outcomes import Notification, NotificationPreference
from app.schemas.notifications import NotificationPreferenceRead, NotificationPreferenceUpsert
from app.services.audit_service import record_audit_log

logger = logging.getLogger("flowsentry.notifications")

SEVERITY_RANK = {
    "informational": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


def _mask_preference_target(channel: str, encrypted_config: str) -> tuple[bool, str | None]:
    if not encrypted_config:
        return False, None
    try:
        cfg = decrypt_json(encrypted_config)
    except Exception:
        return False, None

    if channel == "slack":
        url = str(cfg.get("webhook_url") or "")
        if not url:
            return False, None
        return True, f"https://hooks.slack.com/...{mask_secret(url, 4)}"

    if channel == "email":
        recipients = cfg.get("recipients") or []
        if not recipients:
            return False, None
        masked = []
        for email in recipients[:3]:
            parts = str(email).split("@")
            if len(parts) == 2:
                masked.append(f"{parts[0][:2]}***@{parts[1]}")
        return True, ", ".join(masked) if masked else "Configured"

    return False, None


def to_preference_read(pref: NotificationPreference) -> NotificationPreferenceRead:
    has_cfg, masked = _mask_preference_target(pref.channel, pref.encrypted_config)
    return NotificationPreferenceRead(
        id=pref.id,
        workspace_id=pref.workspace_id,
        channel=pref.channel,
        enabled=pref.enabled,
        has_config=has_cfg,
        masked_target=masked,
        events=pref.events or [],
        min_severity=pref.min_severity,
        suppression_minutes=pref.suppression_minutes,
        updated_at=pref.updated_at,
    )


def list_preferences(db: Session, *, workspace_id: uuid.UUID) -> list[NotificationPreference]:
    return list(
        db.scalars(
            select(NotificationPreference)
            .where(NotificationPreference.workspace_id == workspace_id)
            .order_by(NotificationPreference.channel.asc())
        ).all()
    )


def upsert_preference(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: NotificationPreferenceUpsert,
) -> NotificationPreference:
    existing = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.workspace_id == workspace_id,
            NotificationPreference.channel == payload.channel,
        )
    )

    existing_cfg: dict[str, Any] = {}
    if existing and existing.encrypted_config:
        try:
            existing_cfg = decrypt_json(existing.encrypted_config)
        except Exception:
            existing_cfg = {}

    new_cfg = dict(existing_cfg)
    if payload.channel == "slack" and payload.slack_webhook_url is not None:
        raw_url = payload.slack_webhook_url.strip()
        if raw_url:
            try:
                validated = validate_outbound_url(raw_url)
            except SSRFValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "INVALID_WEBHOOK_URL", "message": str(exc)},
                ) from exc
            new_cfg["webhook_url"] = validated
        else:
            new_cfg.pop("webhook_url", None)

    if payload.channel == "email" and payload.email_recipients is not None:
        new_cfg["recipients"] = [str(r).lower() for r in payload.email_recipients]

    encrypted = encrypt_json(new_cfg)

    if existing is None:
        existing = NotificationPreference(
            workspace_id=workspace_id,
            channel=payload.channel,
            enabled=payload.enabled,
            encrypted_config=encrypted,
            events=list(payload.events),
            min_severity=payload.min_severity,
            suppression_minutes=payload.suppression_minutes,
        )
        db.add(existing)
    else:
        existing.enabled = payload.enabled
        existing.encrypted_config = encrypted
        existing.events = list(payload.events)
        existing.min_severity = payload.min_severity
        existing.suppression_minutes = payload.suppression_minutes

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="notification_preference.updated",
        resource_type="notification_preference",
        resource_id=payload.channel,
        metadata={"channel": payload.channel, "enabled": payload.enabled, "min_severity": payload.min_severity},
    )
    db.commit()
    db.refresh(existing)
    return existing


def _deliver_slack(
    webhook_url: str,
    *,
    title: str,
    body: str,
    transport: httpx.BaseTransport | None = None,
) -> None:
    safe_url = validate_outbound_url(webhook_url)
    with httpx.Client(
        timeout=5.0,
        follow_redirects=False,
        transport=transport or build_ssrf_safe_transport(),
    ) as client:
        resp = client.post(safe_url, json={"text": f"*{title}*\n{body}"})
    if resp.status_code >= 400:
        raise RuntimeError(f"Slack webhook returned HTTP {resp.status_code}")


def _deliver_email(
    recipients: list[str],
    *,
    subject: str,
    body: str,
    smtp_client_factory: Any = smtplib.SMTP,
) -> None:
    settings = get_settings()
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")
    if not recipients:
        raise RuntimeError("No email recipients configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    with smtp_client_factory(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


def attempt_delivery(
    db: Session,
    *,
    notification: Notification,
    pref: NotificationPreference,
    title: str,
    body: str,
    transport: httpx.BaseTransport | None = None,
    smtp_client_factory: Any = smtplib.SMTP,
) -> Notification:
    notification.attempt_count += 1
    try:
        cfg = decrypt_json(pref.encrypted_config)
        if notification.channel == "slack":
            url = str(cfg.get("webhook_url") or "")
            if not url:
                raise RuntimeError("Slack webhook URL is not configured")
            _deliver_slack(url, title=title, body=body, transport=transport)
        elif notification.channel == "email":
            recipients = [str(r) for r in (cfg.get("recipients") or [])]
            _deliver_email(recipients, subject=title, body=body, smtp_client_factory=smtp_client_factory)
        else:
            raise RuntimeError(f"Unsupported notification channel: {notification.channel}")

        notification.status = "sent"
        notification.sent_at = datetime.now(UTC)
        notification.error_message = None
    except Exception as exc:
        notification.status = "failed"
        notification.error_message = str(exc)[:500]
        logger.warning("Notification %s delivery failed: %s", notification.id, exc)

    db.commit()
    db.refresh(notification)
    return notification


def dispatch_incident_event(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident: Incident,
    event_type: str,
    transport: httpx.BaseTransport | None = None,
    smtp_client_factory: Any = smtplib.SMTP,
) -> list[Notification]:
    """Evaluate workspace notification preferences, suppress duplicates, and dispatch."""
    prefs = list(
        db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.workspace_id == workspace_id,
                NotificationPreference.enabled.is_(True),
            )
        ).all()
    )
    if not prefs:
        return []

    inc_rank = SEVERITY_RANK.get(incident.severity, 3)
    now = datetime.now(UTC)
    created: list[Notification] = []

    for pref in prefs:
        if event_type not in (pref.events or []):
            continue
        min_rank = SEVERITY_RANK.get(pref.min_severity, 4)
        if event_type != "incident_resolved" and inc_rank < min_rank:
            continue

        dedup_key = f"{workspace_id}:{incident.id}:{event_type}:{pref.channel}"
        suppressed = False
        if pref.suppression_minutes > 0:
            window_start = now - timedelta(minutes=pref.suppression_minutes)
            recent_sent = db.scalar(
                select(Notification.id).where(
                    Notification.dedup_key == dedup_key,
                    Notification.status == "sent",
                    Notification.created_at >= window_start,
                )
            )
            if recent_sent is not None:
                suppressed = True

        notif = Notification(
            workspace_id=workspace_id,
            incident_id=incident.id,
            channel=pref.channel,
            event_type=event_type,
            dedup_key=dedup_key,
            status="suppressed" if suppressed else "pending",
            attempt_count=0,
        )
        db.add(notif)
        db.flush()

        if suppressed:
            db.commit()
            db.refresh(notif)
            created.append(notif)
            continue

        title = f"[FlowSentry] {incident.severity.upper()} — {incident.title}"
        body = (
            f"Event: {event_type}\n"
            f"Status: {incident.status}\n"
            f"Occurrences: {incident.occurrence_count}\n"
            f"Details: {incident.description or 'See FlowSentry dashboard'}"
        )
        delivered = attempt_delivery(
            db,
            notification=notif,
            pref=pref,
            title=title,
            body=body,
            transport=transport,
            smtp_client_factory=smtp_client_factory,
        )
        created.append(delivered)

    return created


def send_test_notification(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    channel: str,
    transport: httpx.BaseTransport | None = None,
    smtp_client_factory: Any = smtplib.SMTP,
) -> Notification:
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.workspace_id == workspace_id,
            NotificationPreference.channel == channel,
        )
    )
    if pref is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PREFERENCE_NOT_FOUND", "message": f"No {channel} notification preference configured"},
        )

    notif = Notification(
        workspace_id=workspace_id,
        incident_id=None,
        channel=channel,
        event_type="test_delivery",
        dedup_key=f"{workspace_id}:test:{channel}:{uuid.uuid4()}",
        status="pending",
        attempt_count=0,
    )
    db.add(notif)
    db.flush()

    return attempt_delivery(
        db,
        notification=notif,
        pref=pref,
        title="[FlowSentry] Test Notification",
        body="This is a test delivery from your FlowSentry workspace notification settings.",
        transport=transport,
        smtp_client_factory=smtp_client_factory,
    )


def retry_failed_notification(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    notification_id: uuid.UUID,
    transport: httpx.BaseTransport | None = None,
    smtp_client_factory: Any = smtplib.SMTP,
) -> Notification:
    notif = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.workspace_id == workspace_id,
        )
    )
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOTIFICATION_NOT_FOUND", "message": "Notification not found"},
        )
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.workspace_id == workspace_id,
            NotificationPreference.channel == notif.channel,
        )
    )
    if pref is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PREFERENCE_NOT_FOUND", "message": "Channel preference no longer configured"},
        )

    title = f"[FlowSentry] Retry — {notif.event_type}"
    body = f"Retry delivery for workspace notification {notif.id}."
    if notif.incident_id:
        inc = db.get(Incident, notif.incident_id)
        if inc:
            title = f"[FlowSentry] {inc.severity.upper()} — {inc.title}"
            body = f"Event: {notif.event_type}\nStatus: {inc.status}\nDetails: {inc.description or ''}"

    return attempt_delivery(
        db,
        notification=notif,
        pref=pref,
        title=title,
        body=body,
        transport=transport,
        smtp_client_factory=smtp_client_factory,
    )


def list_notifications(
    db: Session, *, workspace_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[Notification], int]:
    total = int(db.scalar(select(func.count(Notification.id)).where(Notification.workspace_id == workspace_id)) or 0)
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.workspace_id == workspace_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return rows, total
