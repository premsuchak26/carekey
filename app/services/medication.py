"""Medication management, scheduling, dose logging, and adherence calculation."""

from datetime import date, datetime, time
from typing import Any, Literal
from uuid import uuid4

from app.constants import (
    DOSE_STATUS_LATE,
    DOSE_STATUS_MISSED,
    DOSE_STATUS_ON_TIME,
    DOSE_STATUS_SKIPPED,
    DOSE_STATUS_TAKEN,
    LATE_THRESHOLD_SECONDS,
    MISSED_THRESHOLD_SECONDS,
)
from app.models import AdherenceSummary, DoseEvent, DoseSchedule, Medication
from app.repositories import RepositoryContainer
from app.services.audit import AuditService


class MedicationService:
    """Handles medication CRUD, schedule generation, dose logging, and adherence."""

    LATE_THRESHOLD_SECONDS = LATE_THRESHOLD_SECONDS
    MISSED_THRESHOLD_SECONDS = MISSED_THRESHOLD_SECONDS

    def __init__(
        self,
        repositories: RepositoryContainer,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repos = repositories
        self.audit = audit_service or AuditService(repositories=repositories)

    @classmethod
    def calculate_dose_status(
        cls,
        scheduled_time: datetime,
        timestamp: datetime,
        status: Literal["taken", "skipped"],
    ) -> Literal["on_time", "late", "missed", "skipped"]:
        """Compute status based on scheduled vs actual administration time."""
        if status == DOSE_STATUS_SKIPPED:
            return DOSE_STATUS_SKIPPED

        diff_seconds = (timestamp - scheduled_time).total_seconds()
        if diff_seconds <= cls.LATE_THRESHOLD_SECONDS:
            return DOSE_STATUS_ON_TIME
        if diff_seconds <= cls.MISSED_THRESHOLD_SECONDS:
            return DOSE_STATUS_LATE
        return DOSE_STATUS_MISSED

    async def add_medication(
        self,
        circle_id: str,
        name: str,
        dosage: str,
        instructions: str = "",
        prescribing_doctor: str = "",
        times_of_day: list[str] | None = None,
        days_of_week: list[int] | None = None,
        dose_amount: str = "1 tablet",
        actor_name: str = "Elder",
    ) -> Medication:
        """Add new medication and associated dosing schedule."""
        med_id = str(uuid4())
        times = times_of_day or ["08:00"]
        days = days_of_week if days_of_week is not None else [0, 1, 2, 3, 4, 5, 6]

        schedule = DoseSchedule(
            medication_id=med_id,
            times_of_day=times,
            days_of_week=days,
            dose_amount=dose_amount,
            max_doses_per_day=len(times),
        )
        await self.repos.schedules.save(schedule.id, schedule)

        medication = Medication(
            id=med_id,
            circle_id=circle_id,
            name=name,
            dosage=dosage,
            instructions=instructions,
            prescribing_doctor=prescribing_doctor,
            schedule=schedule,
        )
        await self.repos.medications.save(medication.id, medication)

        circle = await self.repos.circles.get(circle_id)
        elder_id = circle.elder_id if circle else ""
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=actor_name,
            action="medication.add",
            target=name,
            details={"dosage": dosage, "instructions": instructions},
        )

        return medication

    async def update_medication(
        self,
        circle_id: str,
        medication_id: str,
        name: str,
        dosage: str,
        instructions: str = "",
        prescribing_doctor: str = "",
        times_of_day: list[str] | None = None,
        days_of_week: list[int] | None = None,
        dose_amount: str = "1 tablet",
    ) -> Medication | None:
        """Update existing medication and its schedule."""
        med = await self.repos.medications.get(medication_id)
        if not med or med.circle_id != circle_id:
            return None

        med.name = name
        med.dosage = dosage
        med.instructions = instructions
        med.prescribing_doctor = prescribing_doctor

        times = times_of_day or ["08:00"]
        days = days_of_week if days_of_week is not None else [0, 1, 2, 3, 4, 5, 6]

        if med.schedule:
            med.schedule.times_of_day = times
            med.schedule.days_of_week = days
            med.schedule.dose_amount = dose_amount
            med.schedule.max_doses_per_day = len(times)
            await self.repos.schedules.save(med.schedule.id, med.schedule)
        else:
            schedule = DoseSchedule(
                medication_id=med.id,
                times_of_day=times,
                days_of_week=days,
                dose_amount=dose_amount,
                max_doses_per_day=len(times),
            )
            med.schedule = schedule
            await self.repos.schedules.save(schedule.id, schedule)

        await self.repos.medications.save(med.id, med)
        return med

    async def delete_medication(
        self, circle_id: str, medication_id: str, actor_name: str = "Elder"
    ) -> bool:
        """Delete medication and clean up associated schedules and events."""
        med = await self.repos.medications.get(medication_id)
        if not med or med.circle_id != circle_id:
            return False

        if med.schedule:
            await self.repos.schedules.delete(med.schedule.id)
        await self.repos.medications.delete(medication_id)

        circle = await self.repos.circles.get(circle_id)
        elder_id = circle.elder_id if circle else ""
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=actor_name,
            action="medication.delete",
            target=med.name,
            details={"medication_id": medication_id},
        )
        return True

    async def list_medications(self, circle_id: str) -> list[Medication]:
        """List all medications for a specific circle."""
        return await self.repos.medications.find(lambda m: m.circle_id == circle_id)

    async def log_dose(
        self,
        circle_id: str,
        medication_id: str,
        scheduled_time: datetime,
        status: Literal["taken", "skipped"],
        logged_by: str = "",
        notes: str = "",
        timestamp: datetime | None = None,
        dose_status: Literal["on_time", "late", "missed", "skipped"] | None = None,
    ) -> DoseEvent:
        """Log a dose administration event with computed punctuality status."""
        med = await self.repos.medications.get(medication_id)
        if not med or med.circle_id != circle_id:
            raise ValueError("Medication does not exist in this care circle.")

        log_time = timestamp or datetime.now()
        resolved_status = dose_status or self.calculate_dose_status(
            scheduled_time=scheduled_time,
            timestamp=log_time,
            status=status,
        )

        event = DoseEvent(
            circle_id=circle_id,
            medication_id=medication_id,
            scheduled_time=scheduled_time,
            status=status,
            dose_status=resolved_status,
            timestamp=log_time,
            logged_by=logged_by,
            notes=notes,
        )
        await self.repos.dose_events.save(event.id, event)

        circle = await self.repos.circles.get(circle_id)
        elder_id = circle.elder_id if circle else ""
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=logged_by or "Caregiver",
            action="dose.log",
            target=med.name,
            details={
                "status": status,
                "dose_status": resolved_status,
                "notes": notes,
                "medication_id": medication_id,
            },
            timestamp=log_time,
        )
        return event

    @staticmethod
    def _index_logged_events(events: list[DoseEvent]) -> dict[str, DoseEvent]:
        """Index logged events by medication_id and scheduled HH:MM."""
        logged_map: dict[str, DoseEvent] = {}
        for event in events:
            time_key = event.scheduled_time.strftime("%H:%M")
            logged_map[f"{event.medication_id}:{time_key}"] = event
        return logged_map

    @staticmethod
    def _is_med_active_today(med: Medication, today: date, weekday: int) -> bool:
        """Check if medication is active and scheduled on given day."""
        if not med.schedule:
            return False
        if weekday not in med.schedule.days_of_week:
            return False
        if med.schedule.start_date > today:
            return False
        return not (med.schedule.end_date and med.schedule.end_date < today)

    def _build_dose_entry(
        self,
        med: Medication,
        t_str: str,
        today: date,
        now: datetime,
        logged_map: dict[str, DoseEvent],
    ) -> dict[str, Any] | None:
        """Construct display entry for a specific scheduled time."""
        try:
            hour, minute = map(int, t_str.split(":"))
            sched_dt = datetime.combine(today, time(hour, minute))
        except (ValueError, IndexError):
            return None

        logged_event = logged_map.get(f"{med.id}:{t_str}")
        status: str
        display_status: str
        if logged_event:
            status = logged_event.status
            display_status = logged_event.dose_status
            logged = True
        else:
            logged = False
            status = "pending"
            diff = (now - sched_dt).total_seconds()
            if diff > self.MISSED_THRESHOLD_SECONDS:
                display_status = DOSE_STATUS_MISSED
            elif diff > self.LATE_THRESHOLD_SECONDS:
                display_status = DOSE_STATUS_LATE
            else:
                display_status = "upcoming"

        dose_amount = med.schedule.dose_amount if med.schedule else "1 tablet"
        return {
            "medication_id": med.id,
            "medication_name": med.name,
            "dosage": med.dosage,
            "instructions": med.instructions,
            "dose_amount": dose_amount,
            "time_str": t_str,
            "scheduled_time": sched_dt,
            "logged": logged,
            "status": status,
            "display_status": display_status,
            "event": logged_event,
        }

    async def get_today_doses(
        self, circle_id: str, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve scheduled doses for today with current administration status."""
        today = target_date or datetime.now().date()
        weekday = today.weekday()

        medications = await self.list_medications(circle_id)
        events = await self.repos.dose_events.find(
            lambda e: e.circle_id == circle_id and e.scheduled_time.date() == today
        )
        logged_map = self._index_logged_events(events)

        doses: list[dict[str, Any]] = []
        now = datetime.now()

        for med in medications:
            if not self._is_med_active_today(med, today, weekday) or not med.schedule:
                continue

            for t_str in med.schedule.times_of_day:
                entry = self._build_dose_entry(med, t_str, today, now, logged_map)
                if entry is not None:
                    doses.append(entry)

        doses.sort(key=lambda d: str(d["scheduled_time"]))
        return doses

    async def get_adherence_summary(self, circle_id: str) -> list[AdherenceSummary]:
        """Compute adherence statistics and compliance streak per medication."""
        medications = await self.list_medications(circle_id)
        events = await self.repos.dose_events.find(lambda e: e.circle_id == circle_id)

        summaries: list[AdherenceSummary] = []
        for med in medications:
            med_events = [e for e in events if e.medication_id == med.id]
            total = len(med_events)
            taken = sum(1 for e in med_events if e.status == DOSE_STATUS_TAKEN)
            on_time = sum(1 for e in med_events if e.dose_status == DOSE_STATUS_ON_TIME)
            late = sum(1 for e in med_events if e.dose_status == DOSE_STATUS_LATE)
            missed = sum(1 for e in med_events if e.dose_status == DOSE_STATUS_MISSED)
            skipped = sum(1 for e in med_events if e.status == DOSE_STATUS_SKIPPED)

            pct = (taken / total * 100.0) if total > 0 else 100.0

            sorted_events = sorted(med_events, key=lambda e: e.scheduled_time, reverse=True)
            streak = 0
            for ev in sorted_events:
                if ev.status == DOSE_STATUS_TAKEN:
                    streak += 1
                else:
                    break

            summaries.append(
                AdherenceSummary(
                    medication_id=med.id,
                    medication_name=med.name,
                    total_doses=total,
                    taken_doses=taken,
                    on_time_doses=on_time,
                    late_doses=late,
                    missed_doses=missed,
                    skipped_doses=skipped,
                    adherence_percentage=round(pct, 1),
                    streak_days=streak,
                )
            )

        return summaries

    async def get_overall_streak(self, circle_id: str) -> int:
        """Compute overall circle-wide consecutive taken doses streak."""
        events = await self.repos.dose_events.find(lambda e: e.circle_id == circle_id)
        if not events:
            return 0
        sorted_events = sorted(events, key=lambda e: e.scheduled_time, reverse=True)
        streak = 0
        for ev in sorted_events:
            if ev.status == DOSE_STATUS_TAKEN:
                streak += 1
            else:
                break
        return streak
