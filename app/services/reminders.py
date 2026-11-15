"""Stateless reminder service managing escalation ladders and appointment reminders."""

import datetime as dt
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import Settings
from app.constants import (
    ACTION_CALL_ME,
    ACTION_SNOOZE,
    ACTION_TOOK_IT,
    ALREADY_HANDLED_WINDOW_SECONDS,
    DEFAULT_TIMEZONE,
    DOSE_STATUS_MISSED,
    DOSE_STATUS_SKIPPED,
    DOSE_STATUS_TAKEN,
    STAGE_10M_BEFORE,
    STAGE_15M_LATE,
    STAGE_60M_MISSED,
    STAGE_APPT_2H,
    STAGE_APPT_24H,
)
from app.models import (
    Appointment,
    CareCircle,
    Elder,
    Medication,
    Member,
    MemberRole,
    ReminderSent,
)
from app.repositories import RepositoryContainer
from app.services.action_tokens import ActionTokenManager
from app.services.audit import AuditService
from app.services.email import EmailSenderProtocol
from app.services.medication import MedicationService

logger = logging.getLogger(__name__)


def _build_reminder_html(
    name: str,
    med_name: str,
    dosage: str,
    time_str: str,
    url_took: str,
    url_snooze: str,
    url_call: str,
    is_nudge: bool = False,
) -> str:
    """Build accessible, high-contrast HTML email body for medication reminders."""
    title = "Friendly Nudge" if is_nudge else "Medication Reminder"
    lead = (
        f"Your <strong>{med_name}</strong> ({dosage}) was scheduled for "
        f"<strong>{time_str}</strong>."
        if is_nudge
        else f"It is time for your <strong>{med_name}</strong> ({dosage}) "
        f"scheduled for <strong>{time_str}</strong>."
    )
    btn_style = (
        "display:inline-block;color:#fff;padding:12px 24px;"
        "font-size:20px;font-weight:bold;text-decoration:none;border-radius:8px;"
    )
    return (
        f"<div style='font-family:sans-serif;font-size:20px;line-height:1.6;'>"
        f"<h2>{title}</h2>"
        f"<p>Hello <strong>{name}</strong>,</p>"
        f"<p>{lead}</p>"
        f"<div style='margin-top:24px;'>"
        f"<p><a href='{url_took}' style='{btn_style}background:#059669;'>I Took It</a></p>"
        f"<p><a href='{url_snooze}' style='{btn_style}background:#4f46e5;'>Snooze 15 min</a></p>"
        f"<p><a href='{url_call}' style='{btn_style}background:#dc2626;'>Call Me</a></p>"
        f"</div>"
        f"</div>"
    )


def _build_missed_html(
    cg_name: str, elder_name: str, med_name: str, dosage: str, time_str: str
) -> str:
    """Build accessible HTML alert for missed medication."""
    return (
        f"<div style='font-family:sans-serif;font-size:20px;line-height:1.6;'>"
        f"<h2 style='color:#dc2626;'>Missed Dose Alert</h2>"
        f"<p>Hello <strong>{cg_name}</strong>,</p>"
        f"<p><strong>{elder_name}</strong> has missed their scheduled dose of "
        f"<strong>{med_name}</strong> ({dosage}) at <strong>{time_str}</strong>.</p>"
        f"<p>It is now over 60 minutes late and has been recorded as missed.</p>"
        f"<p>Please contact them to offer support.</p>"
        f"</div>"
    )


def _build_appointment_html(
    name: str, doctor: str, place: str, time_str: str, notes: str, is_2h: bool = False
) -> str:
    """Build accessible HTML body for appointment reminder."""
    timeframe = "in about 2 hours" if is_2h else "tomorrow"
    return (
        f"<div style='font-family:sans-serif;font-size:20px;line-height:1.6;'>"
        f"<h2>Upcoming Appointment Reminder</h2>"
        f"<p>Hello <strong>{name}</strong>,</p>"
        f"<p>Reminder of your appointment scheduled for {timeframe}:</p>"
        f"<ul>"
        f"<li><strong>Doctor / Specialist:</strong> {doctor}</li>"
        f"<li><strong>Location:</strong> {place}</li>"
        f"<li><strong>Date & Time:</strong> {time_str}</li>"
        f"<li><strong>Notes:</strong> {notes or 'None'}</li>"
        f"</ul>"
        f"</div>"
    )


class ReminderService:
    """Evaluates due medications and appointments, sending escalations and reminders."""

    def __init__(
        self,
        repos: RepositoryContainer,
        settings: Settings,
        email_sender: EmailSenderProtocol,
        token_manager: ActionTokenManager,
        medication_service: MedicationService,
        audit_service: AuditService,
    ) -> None:
        self.repos = repos
        self.settings = settings
        self.email_sender = email_sender
        self.token_manager = token_manager
        self.medication_service = medication_service
        self.audit_service = audit_service

    def _build_action_urls(
        self, circle_id: str, med_id: str, time_str: str
    ) -> tuple[str, str, str]:
        """Generate signed single-use action URLs for an email notification."""
        t_took = self.token_manager.create_action_token(
            circle_id, med_id, time_str, ACTION_TOOK_IT
        )
        t_snooze = self.token_manager.create_action_token(
            circle_id, med_id, time_str, ACTION_SNOOZE
        )
        t_call = self.token_manager.create_action_token(
            circle_id, med_id, time_str, ACTION_CALL_ME
        )
        base = self.settings.app_base_url
        return (
            f"{base}/actions/confirm?token={t_took}",
            f"{base}/actions/confirm?token={t_snooze}",
            f"{base}/actions/confirm?token={t_call}",
        )

    async def _send_elder_dose_reminder(
        self,
        circle_id: str,
        elder: Elder,
        med: Medication,
        time_str: str,
        scheduled_key: str,
        stage: str,
        is_nudge: bool,
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> bool:
        """Send a 10m-before or 15m-late reminder email to the elder if not already sent."""
        key = ("dose", med.id, scheduled_key, stage, elder.email.lower())
        if key in sent_set:
            return False

        url_took, url_snooze, url_call = self._build_action_urls(circle_id, med.id, time_str)
        if is_nudge:
            subject = f"Friendly Nudge: {med.name} was scheduled for {time_str}"
            text_body = (
                f"Hello {elder.name},\n\n"
                f"Just checking in! Your {med.name} was scheduled for {time_str}.\n"
                f"Tap below:\n"
                f"I took it: {url_took}\n"
                f"Snooze 15 min: {url_snooze}\n"
                f"Call me: {url_call}\n"
            )
        else:
            subject = f"Medication Reminder: Time to take {med.name} ({med.dosage})"
            text_body = (
                f"Hello {elder.name},\n\n"
                f"It is time to take your {med.name} ({med.dosage}) scheduled for {time_str}.\n\n"
                f"Tap an action below:\n"
                f"1. I took it: {url_took}\n"
                f"2. Snooze 15 min: {url_snooze}\n"
                f"3. Call me: {url_call}\n\n"
                f"- CareKey"
            )

        html_body = _build_reminder_html(
            name=elder.name,
            med_name=med.name,
            dosage=med.dosage,
            time_str=time_str,
            url_took=url_took,
            url_snooze=url_snooze,
            url_call=url_call,
            is_nudge=is_nudge,
        )
        await self.email_sender.send_email(elder.email, subject, text_body, html_body)
        record = ReminderSent(
            circle_id=circle_id,
            target_type="dose",
            target_id=med.id,
            scheduled_time=scheduled_key,
            stage=stage,
            recipient_email=elder.email,
        )
        await self.repos.reminders.save(record.id, record)
        sent_set.add(key)
        return True

    async def _send_missed_dose_escalation(
        self,
        circle_id: str,
        elder: Elder,
        med: Medication,
        caregivers: list[Member],
        scheduled_local: dt.datetime,
        scheduled_key: str,
        time_str: str,
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> int:
        """Record missed dose and alert caregivers after 60 minutes."""
        stage = STAGE_60M_MISSED
        needs_alert = any(
            ("dose", med.id, scheduled_key, stage, cg.email.lower()) not in sent_set
            for cg in caregivers
        )
        if not needs_alert:
            return 0

        try:
            await self.medication_service.log_dose(
                circle_id=circle_id,
                medication_id=med.id,
                scheduled_time=scheduled_local.replace(tzinfo=None),
                status=DOSE_STATUS_SKIPPED,
                dose_status=DOSE_STATUS_MISSED,
                logged_by="System (Escalation)",
                notes="Automatically marked missed after 60 minutes",
            )
        except (ValueError, KeyError) as exc:
            logger.debug("Dose already logged: %s", exc)

        sent = 0
        for cg in caregivers:
            key = ("dose", med.id, scheduled_key, stage, cg.email.lower())
            if key in sent_set:
                continue
            subject = f"Missed Medication Alert: {elder.name} missed {med.name}"
            text_body = (
                f"Hello {cg.name},\n\n"
                f"Alert: {elder.name} did not log their {med.name} ({med.dosage}) "
                f"scheduled for {time_str}.\n"
                f"It is over 60 minutes late and recorded as missed.\n"
                f"Please check in with {elder.name}.\n\n"
                f"- CareKey"
            )
            html_body = _build_missed_html(
                cg_name=cg.name,
                elder_name=elder.name,
                med_name=med.name,
                dosage=med.dosage,
                time_str=time_str,
            )
            await self.email_sender.send_email(cg.email, subject, text_body, html_body)
            record = ReminderSent(
                circle_id=circle_id,
                target_type="dose",
                target_id=med.id,
                scheduled_time=scheduled_key,
                stage=stage,
                recipient_email=cg.email,
            )
            await self.repos.reminders.save(record.id, record)
            sent_set.add(key)
            sent += 1
        return sent

    @staticmethod
    def _is_dose_already_handled(
        circle_id: str,
        med_id: str,
        scheduled_local_naive: dt.datetime,
        dose_events: list[Any],
    ) -> bool:
        """Check if a dose was already logged as taken or skipped near the scheduled time."""
        return any(
            e.circle_id == circle_id
            and e.medication_id == med_id
            and e.status in (DOSE_STATUS_TAKEN, DOSE_STATUS_SKIPPED)
            and abs((e.scheduled_time - scheduled_local_naive).total_seconds())
            < ALREADY_HANDLED_WINDOW_SECONDS
            for e in dose_events
        )

    async def _process_medication_time_slot(
        self,
        circle_id: str,
        elder: Elder,
        med: Medication,
        time_str: str,
        elder_local_now: dt.datetime,
        dose_events: list[Any],
        caregivers: list[Member],
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> int:
        """Process a single scheduled time slot for a medication."""
        try:
            parts = time_str.split(":")
            hour_int, min_int = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 0

        scheduled_local = elder_local_now.replace(
            hour=hour_int, minute=min_int, second=0, microsecond=0
        )
        scheduled_key = scheduled_local.strftime("%Y-%m-%d %H:%M")

        if self._is_dose_already_handled(
            circle_id, med.id, scheduled_local.replace(tzinfo=None), dose_events
        ):
            return 0

        diff_minutes = (elder_local_now - scheduled_local).total_seconds() / 60

        if -10 <= diff_minutes < 15:
            sent = await self._send_elder_dose_reminder(
                circle_id, elder, med, time_str, scheduled_key, STAGE_10M_BEFORE, False, sent_set
            )
            return 1 if sent else 0
        if 15 <= diff_minutes < 60:
            sent = await self._send_elder_dose_reminder(
                circle_id, elder, med, time_str, scheduled_key, STAGE_15M_LATE, True, sent_set
            )
            return 1 if sent else 0
        if diff_minutes >= 60:
            return await self._send_missed_dose_escalation(
                circle_id,
                elder,
                med,
                caregivers,
                scheduled_local,
                scheduled_key,
                time_str,
                sent_set,
            )
        return 0

    async def _process_circle_medications(
        self,
        circle: CareCircle,
        elder: Elder | None,
        meds: list[Medication],
        dose_events: list[Any],
        members: list[Member],
        current_utc: dt.datetime,
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> int:
        """Process medication reminder ladders for a single care circle."""
        if not elder or not elder.email:
            return 0

        try:
            elder_tz = ZoneInfo(elder.timezone)
        except (KeyError, ZoneInfoNotFoundError):
            elder_tz = ZoneInfo(DEFAULT_TIMEZONE)

        elder_local_now = current_utc.astimezone(elder_tz)
        local_weekday = elder_local_now.weekday()
        caregivers = [
            m
            for m in members
            if m.role in (MemberRole.MANAGER, MemberRole.HELPER)
            and not m.revoked_at
            and m.email
        ]

        sent = 0
        for med in meds:
            schedule = med.schedule
            if not schedule or not schedule.times_of_day:
                continue
            if schedule.days_of_week and local_weekday not in schedule.days_of_week:
                continue
            for time_str in schedule.times_of_day:
                sent += await self._process_medication_time_slot(
                    circle.id,
                    elder,
                    med,
                    time_str,
                    elder_local_now,
                    dose_events,
                    caregivers,
                    sent_set,
                )
        return sent

    async def _send_single_appointment_reminder(
        self,
        circle_id: str,
        appt: Appointment,
        appt_key: str,
        stage: str,
        email: str,
        name: str,
        formatted_time: str,
        is_2h: bool,
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> bool:
        """Send an appointment reminder to an elder or caregiver if not yet sent."""
        key = ("appointment", appt.id, appt_key, stage, email.lower())
        if key in sent_set:
            return False

        timeframe_label = "In 2 Hours" if is_2h else "Tomorrow"
        lead = "in about 2 hours" if is_2h else "tomorrow"
        subject = f"Appointment Reminder ({timeframe_label}): {appt.doctor} at {appt.place}"
        text_body = (
            f"Hello {name},\n\n"
            f"Reminder: Appointment with {appt.doctor} {lead}.\n"
            f"Location: {appt.place}\n"
            f"Time: {formatted_time}\n"
            f"Notes: {appt.notes or 'None'}\n\n"
            f"- CareKey"
        )
        html_body = _build_appointment_html(
            name=name,
            doctor=appt.doctor,
            place=appt.place,
            time_str=formatted_time,
            notes=appt.notes,
            is_2h=is_2h,
        )
        await self.email_sender.send_email(email, subject, text_body, html_body)
        record = ReminderSent(
            circle_id=circle_id,
            target_type="appointment",
            target_id=appt.id,
            scheduled_time=appt_key,
            stage=stage,
            recipient_email=email,
        )
        await self.repos.reminders.save(record.id, record)
        sent_set.add(key)
        return True

    async def _process_appointment(
        self,
        appt: Appointment,
        circle: CareCircle,
        elder: Elder | None,
        caregivers: list[Member],
        current_utc: dt.datetime,
        sent_set: set[tuple[str, str, str, str, str]],
    ) -> int:
        """Evaluate and send 24h/2h reminders for a single appointment."""
        appt_dt = appt.datetime
        if appt_dt.tzinfo is None:
            tz_name = elder.timezone if elder else DEFAULT_TIMEZONE
            try:
                tz = ZoneInfo(tz_name)
            except (KeyError, ZoneInfoNotFoundError):
                tz = ZoneInfo(DEFAULT_TIMEZONE)
            appt_utc = appt_dt.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))
        else:
            appt_utc = appt_dt.astimezone(ZoneInfo("UTC"))

        diff_hours = (appt_utc - current_utc).total_seconds() / 3600
        appt_key = appt_utc.strftime("%Y-%m-%d %H:%M UTC")

        recipients: list[tuple[str, str]] = []
        if elder and elder.email:
            recipients.append((elder.email, elder.name))
        for cg in caregivers:
            recipients.append((cg.email, cg.name))

        formatted_time = appt.datetime.strftime("%b %d, %Y at %I:%M %p")
        sent = 0

        if 2 < diff_hours <= 24:
            for email, name in recipients:
                if await self._send_single_appointment_reminder(
                    circle.id,
                    appt,
                    appt_key,
                    STAGE_APPT_24H,
                    email,
                    name,
                    formatted_time,
                    False,
                    sent_set,
                ):
                    sent += 1
        elif 0 <= diff_hours <= 2:
            for email, name in recipients:
                if await self._send_single_appointment_reminder(
                    circle.id,
                    appt,
                    appt_key,
                    STAGE_APPT_2H,
                    email,
                    name,
                    formatted_time,
                    True,
                    sent_set,
                ):
                    sent += 1

        return sent

    async def process_tick(self, now: dt.datetime | None = None) -> dict[str, Any]:
        """Process a single reminder tick cycle idempotently."""
        if now is None:
            current_utc = dt.datetime.now(ZoneInfo("UTC"))
        elif now.tzinfo is None:
            current_utc = now.replace(tzinfo=ZoneInfo("UTC"))
        else:
            current_utc = now.astimezone(ZoneInfo("UTC"))

        circles = await self.repos.circles.find(lambda _: True)
        elders = await self.repos.elders.find(lambda _: True)
        members = await self.repos.members.find(lambda _: True)
        medications = await self.repos.medications.find(lambda _: True)
        appointments = await self.repos.appointments.find(lambda _: True)
        dose_events = await self.repos.dose_events.find(lambda _: True)
        sent_records = await self.repos.reminders.find(lambda _: True)

        elder_map: dict[str, Elder] = {e.id: e for e in elders}
        circle_map = {c.id: c for c in circles}

        members_by_circle: dict[str, list[Member]] = {}
        for m in members:
            members_by_circle.setdefault(m.circle_id, []).append(m)

        meds_by_circle: dict[str, list[Medication]] = {}
        for med in medications:
            meds_by_circle.setdefault(med.circle_id, []).append(med)

        sent_set: set[tuple[str, str, str, str, str]] = {
            (
                r.target_type,
                r.target_id,
                r.scheduled_time,
                r.stage,
                r.recipient_email.lower(),
            )
            for r in sent_records
        }

        sent_count = 0

        # --- 1. Medication Escalation Ladder ---
        for circle in circles:
            elder = elder_map.get(circle.elder_id)
            circle_meds = meds_by_circle.get(circle.id, [])
            circle_members = members_by_circle.get(circle.id, [])
            sent_count += await self._process_circle_medications(
                circle,
                elder,
                circle_meds,
                dose_events,
                circle_members,
                current_utc,
                sent_set,
            )

        # --- 2. Appointment Reminders ---
        for appt in appointments:
            appt_circle = circle_map.get(appt.circle_id)
            if not appt_circle:
                continue
            elder = elder_map.get(appt_circle.elder_id)
            caregivers = [
                m
                for m in members_by_circle.get(appt_circle.id, [])
                if m.role in (MemberRole.MANAGER, MemberRole.HELPER)
                and not m.revoked_at
                and m.email
            ]
            sent_count += await self._process_appointment(
                appt, appt_circle, elder, caregivers, current_utc, sent_set
            )

        return {
            "status": "ok",
            "processed_circles": len(circles),
            "sent_reminders": sent_count,
        }
