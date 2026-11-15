"""Signed, single-use, expiring action tokens for one-tap email actions."""

import base64
import datetime as dt
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.models import MemberRole, UsedActionToken
from app.repositories import RepositoryContainer
from app.services.audit import AuditService
from app.services.email import EmailSenderProtocol


@dataclass(frozen=True)
class ActionTokenPayload:
    """Decoded one-tap action token payload."""

    circle_id: str
    medication_id: str
    scheduled_time: str
    action: str
    token_id: str
    exp: int


class ActionTokenManager:
    """Generates, signs, verifies, and executes one-tap email action tokens."""

    def __init__(self, settings: Settings, repos: RepositoryContainer) -> None:
        self.settings = settings
        self.repos = repos

    def _sign(self, data: bytes) -> str:
        """Compute HMAC-SHA256 hex digest using application secret key."""
        return hmac.new(
            self.settings.secret_key.encode("utf-8"),
            data,
            hashlib.sha256,
        ).hexdigest()

    def create_action_token(
        self,
        circle_id: str,
        medication_id: str,
        scheduled_time: str,
        action: str,
        expiry_hours: int = 24,
    ) -> str:
        """Create a signed, expiring action token string."""
        token_id = str(uuid4())
        exp = int(time.time() + (expiry_hours * 3600))
        data = {
            "circle_id": circle_id,
            "medication_id": medication_id,
            "scheduled_time": scheduled_time,
            "action": action,
            "token_id": token_id,
            "exp": exp,
        }
        raw_json = json.dumps(data, sort_keys=True).encode("utf-8")
        b64_part = base64.urlsafe_b64encode(raw_json).decode("utf-8")
        sig = self._sign(b64_part.encode("utf-8"))
        return f"{b64_part}.{sig}"

    async def verify_token(self, token: str) -> ActionTokenPayload | None:
        """Verify token signature, expiry, and single-use status."""
        parts = token.strip().split(".")
        if len(parts) != 2:
            return None
        b64_part, sig = parts

        expected_sig = self._sign(b64_part.encode("utf-8"))
        if not hmac.compare_digest(sig, expected_sig):
            return None

        try:
            raw_json = base64.urlsafe_b64decode(b64_part.encode("utf-8"))
            data: dict[str, Any] = json.loads(raw_json.decode("utf-8"))
        except Exception:
            return None

        exp = int(data.get("exp", 0))
        if time.time() > exp:
            return None

        token_id = str(data.get("token_id", ""))
        if not token_id:
            return None

        # Check single-use
        already_used = await self.repos.used_tokens.find(lambda t: t.token_id == token_id)
        if already_used:
            return None

        return ActionTokenPayload(
            circle_id=str(data.get("circle_id", "")),
            medication_id=str(data.get("medication_id", "")),
            scheduled_time=str(data.get("scheduled_time", "")),
            action=str(data.get("action", "")),
            token_id=token_id,
            exp=exp,
        )

    async def consume_token(self, token_id: str, action: str) -> None:
        """Record token consumption to enforce single-use."""
        used = UsedActionToken(token_id=token_id, action=action)
        await self.repos.used_tokens.save(used.id, used)

    async def execute_action(
        self,
        payload: ActionTokenPayload,
        medication_service: Any,
        email_sender: EmailSenderProtocol,
        audit_service: AuditService,
    ) -> dict[str, Any]:
        """Consume token and execute the corresponding action."""
        await self.consume_token(payload.token_id, payload.action)

        circle = await self.repos.circles.get(payload.circle_id)
        elder_id = circle.elder_id if circle else ""
        med = await self.repos.medications.get(payload.medication_id)
        med_name = med.name if med else "Medication"

        result: dict[str, Any] = {
            "action": payload.action,
            "medication_name": med_name,
            "scheduled_time": payload.scheduled_time,
        }

        scheduled_dt = dt.datetime.now()
        if ":" in payload.scheduled_time:
            try:
                parts = payload.scheduled_time.split(":")
                hour = int(parts[0])
                minute = int(parts[1][:2])
                scheduled_dt = scheduled_dt.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
            except Exception:
                pass

        if payload.action in ("took_it", "taken"):
            await medication_service.log_dose(
                circle_id=payload.circle_id,
                medication_id=payload.medication_id,
                scheduled_time=scheduled_dt,
                status="taken",
                logged_by="Elder (One-Tap Link)",
                notes=f"Logged via one-tap email action for {payload.scheduled_time}",
            )
            await audit_service.log_event(
                elder_id=elder_id,
                circle_id=payload.circle_id,
                actor="Elder (One-Tap Link)",
                action="action.took_it",
                target=med_name,
                details={
                    "scheduled_time": payload.scheduled_time,
                    "token_id": payload.token_id,
                },
            )
            result["status"] = "Dose logged successfully as taken."

        elif payload.action == "snooze":
            # Record snooze audit entry
            await audit_service.log_event(
                elder_id=elder_id,
                circle_id=payload.circle_id,
                actor="Elder (One-Tap Link)",
                action="action.snooze",
                target=med_name,
                details={
                    "scheduled_time": payload.scheduled_time,
                    "snooze_minutes": 15,
                    "token_id": payload.token_id,
                },
            )
            result["status"] = "Reminder snoozed for 15 minutes."

        elif payload.action == "call_me":
            # Alert circle caretakers (MANAGER and HELPER)
            caregivers = await self.repos.members.find(
                lambda m: (
                    m.circle_id == payload.circle_id
                    and m.role in (MemberRole.MANAGER, MemberRole.HELPER)
                    and not m.revoked_at
                )
            )
            elder = await self.repos.elders.get(elder_id) if elder_id else None
            elder_display = elder.name if elder else "The elder"

            for cg in caregivers:
                await email_sender.send_email(
                    to=cg.email,
                    subject=f"Urgent: {elder_display} requested a call (CareKey)",
                    text_body=(
                        f"Hello {cg.name},\n\n"
                        f"{elder_display} clicked 'Call me' regarding their {med_name} "
                        f"dose scheduled for {payload.scheduled_time}.\n"
                        f"Please call them as soon as possible.\n\n"
                        f"- CareKey Circle"
                    ),
                    html_body=(
                        f"<p>Hello {cg.name},</p>"
                        f"<p><strong>{elder_display}</strong> clicked <em>Call me</em> regarding "
                        f"their {med_name} dose scheduled for {payload.scheduled_time}.</p>"
                        f"<p>Please call them as soon as possible.</p>"
                    ),
                )

            await audit_service.log_event(
                elder_id=elder_id,
                circle_id=payload.circle_id,
                actor="Elder (One-Tap Link)",
                action="action.call_me",
                target=med_name,
                details={
                    "scheduled_time": payload.scheduled_time,
                    "caregivers_alerted": [cg.email for cg in caregivers],
                    "token_id": payload.token_id,
                },
            )
            result["status"] = "Your care circle has been notified to call you."

        return result
