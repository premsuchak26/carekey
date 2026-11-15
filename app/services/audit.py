"""Tamper-evident audit logging service with cryptographic hash chaining."""

import datetime as dt
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.models import AuditEntry
from app.repositories import RepositoryContainer

GENESIS_HASH = "0" * 64
SENSITIVE_KEYS = {"passcode", "key", "key_hash", "salt", "secret", "token", "password"}


def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive fields such as passcodes and raw secrets from audit logs."""
    cleaned: dict[str, Any] = {}
    for k, v in details.items():
        if k.lower() in SENSITIVE_KEYS:
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = sanitize_details(v)
        else:
            cleaned[k] = v
    return cleaned


def canonical_entry_payload(
    entry_id: str,
    elder_id: str,
    actor: str,
    action: str,
    target: str,
    timestamp: dt.datetime,
    details: dict[str, Any],
    circle_id: str = "",
) -> dict[str, Any]:
    """Create a standardized dictionary representation for canonical JSON hashing."""
    return {
        "action": action,
        "actor": actor,
        "circle_id": circle_id,
        "details": details,
        "elder_id": elder_id,
        "id": entry_id,
        "target": target,
        "timestamp": timestamp.isoformat(),
    }


def compute_entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """Compute SHA-256 hash over prev_hash concatenated with canonical JSON of entry."""
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    content = (prev_hash + canonical_json).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def verify_chain(entries: list[AuditEntry]) -> tuple[bool, str]:
    """Verify cryptographic integrity of an ordered audit log chain.

    Returns:
        tuple[bool, str]: (True, "OK") if all hashes and prev_hash links match,
        or (False, description_of_first_broken_entry).
    """
    if not entries:
        return True, "Audit log is empty."

    # Sort strictly by timestamp ascending
    sorted_entries = sorted(entries, key=lambda e: e.timestamp)

    for i, entry in enumerate(sorted_entries):
        payload = canonical_entry_payload(
            entry_id=entry.id,
            elder_id=entry.elder_id,
            actor=entry.actor,
            action=entry.action,
            target=entry.target,
            timestamp=entry.timestamp,
            details=entry.details,
            circle_id=entry.circle_id,
        )

        expected_prev = GENESIS_HASH if i == 0 else sorted_entries[i - 1].hash
        if entry.prev_hash != expected_prev:
            return (
                False,
                f"Broken chain link at entry '{entry.id}' ({entry.action} by {entry.actor}): "
                f"expected prev_hash '{expected_prev}', found '{entry.prev_hash}'.",
            )

        expected_hash = compute_entry_hash(entry.prev_hash, payload)
        if entry.hash != expected_hash:
            return (
                False,
                f"Hash mismatch / data tampering at entry '{entry.id}' "
                f"({entry.action} by {entry.actor}): "
                f"expected '{expected_hash}', found '{entry.hash}'.",
            )

    return True, "Audit log integrity verified intact. All cryptographic links valid."


class AuditService:
    """Service managing append-only, tamper-evident audit trail."""

    def __init__(self, repositories: RepositoryContainer) -> None:
        self.repos = repositories

    async def log_event(
        self,
        elder_id: str,
        actor: str,
        action: str,
        target: str,
        details: dict[str, Any] | None = None,
        circle_id: str = "",
        timestamp: dt.datetime | None = None,
    ) -> AuditEntry:
        """Append an audit entry to the circle's tamper-evident chain."""
        clean_details = sanitize_details(details or {})
        entry_time = timestamp or dt.datetime.now()
        entry_id = str(uuid4())

        # Retrieve existing entries to locate current head hash
        existing = await self.repos.audit_log.find(
            lambda e: e.circle_id == circle_id if circle_id else e.elder_id == elder_id
        )
        if existing:
            sorted_existing = sorted(existing, key=lambda e: e.timestamp)
            prev_hash = sorted_existing[-1].hash
        else:
            prev_hash = GENESIS_HASH

        payload = canonical_entry_payload(
            entry_id=entry_id,
            elder_id=elder_id,
            actor=actor,
            action=action,
            target=target,
            timestamp=entry_time,
            details=clean_details,
            circle_id=circle_id,
        )
        entry_hash = compute_entry_hash(prev_hash, payload)

        entry = AuditEntry(
            id=entry_id,
            elder_id=elder_id,
            actor=actor,
            action=action,
            target=target,
            timestamp=entry_time,
            details=clean_details,
            prev_hash=prev_hash,
            hash=entry_hash,
            circle_id=circle_id,
        )
        await self.repos.audit_log.save(entry.id, entry)
        return entry

    async def get_entries(
        self, circle_id: str, actor_filter: str | None = None
    ) -> list[AuditEntry]:
        """Retrieve audit entries for a circle, sorted newest first, with optional actor filter."""
        entries = await self.repos.audit_log.find(lambda e: e.circle_id == circle_id)
        if actor_filter and actor_filter.strip():
            entries = [
                e for e in entries if e.actor.strip().lower() == actor_filter.strip().lower()
            ]
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)

    async def get_all_actors(self, circle_id: str) -> list[str]:
        """Get unique actors who have touched data in this circle."""
        entries = await self.repos.audit_log.find(lambda e: e.circle_id == circle_id)
        actors = {e.actor for e in entries if e.actor}
        return sorted(actors)

    async def verify_circle_chain(self, circle_id: str) -> tuple[bool, str]:
        """Verify chain integrity for all entries in a care circle."""
        entries = await self.repos.audit_log.find(lambda e: e.circle_id == circle_id)
        return verify_chain(entries)

    @staticmethod
    def format_sentence(entry: AuditEntry) -> str:
        """Convert a structured audit entry into a human-friendly plain-language sentence."""
        time_str = entry.timestamp.strftime("%b %d, %Y at %I:%M %p")
        actor = entry.actor or "Someone"
        target = entry.target
        details = entry.details or {}

        match entry.action:
            case "auth.login":
                return f"{actor} signed in to the care circle on {time_str}."
            case "auth.login_failed":
                return f"An unrecognized sign-in attempt was rejected on {time_str}."
            case "auth.logout":
                return f"{actor} signed out on {time_str}."
            case "key.issue":
                role = details.get("role", "member")
                name = details.get("member_name", target)
                return f"{actor} created an access key for {name} with role {role} on {time_str}."
            case "key.revoke":
                name = details.get("member_name", target)
                return f"{actor} revoked access for {name} on {time_str}."
            case "proposal.create":
                med_name = details.get("medication_name", target)
                act = details.get("action", "change")
                risk = details.get("risk_level", "NORMAL")
                reason = details.get("reason", "")
                reason_part = f" Reason: '{reason}'." if reason else ""
                return (
                    f"{actor} submitted a {risk}-risk request to {act} medication '{med_name}' "
                    f"on {time_str}.{reason_part}"
                )
            case "proposal.approve":
                med_name = details.get("medication_name", target)
                return f"{actor} approved the medication change for '{med_name}' on {time_str}."
            case "proposal.reject":
                med_name = details.get("medication_name", target)
                reason = details.get("rejection_reason", "")
                reason_part = f" Reason: '{reason}'." if reason else ""
                return (
                    f"{actor} rejected the medication change for '{med_name}' "
                    f"on {time_str}.{reason_part}"
                )
            case "proposal.emergency" | "emergency_override.medication":
                med_name = details.get("medication_name", target)
                act = details.get("action", "modify")
                reason = details.get("reason", "")
                return (
                    f"EMERGENCY OVERRIDE: {actor} immediately applied a change to "
                    f"{act} '{med_name}' on {time_str}. Stated emergency reason: '{reason}'."
                )
            case "dose.log":
                status = details.get("status", "taken")
                dose_status = details.get("dose_status", "on time")
                return (
                    f"{actor} marked dose of '{target}' as {status} ({dose_status}) on {time_str}."
                )
            case "medication.add":
                return f"{actor} added new medication '{target}' on {time_str}."
            case "medication.edit":
                return f"{actor} updated medication '{target}' on {time_str}."
            case "medication.delete":
                return f"{actor} removed medication '{target}' on {time_str}."
            case "appointment.add":
                return f"{actor} scheduled an appointment with {target} on {time_str}."
            case "appointment.delete":
                return f"{actor} cancelled an appointment with {target} on {time_str}."
            case _:
                return f"{actor} performed action '{entry.action}' on '{target}' on {time_str}."
