"""Appointment management service."""

from datetime import datetime

from app.models import Appointment
from app.repositories import RepositoryContainer


class AppointmentService:
    """Handles healthcare appointments scheduling, listing, and updates."""

    def __init__(self, repositories: RepositoryContainer) -> None:
        self.repos = repositories

    async def add_appointment(
        self,
        circle_id: str,
        doctor: str,
        place: str,
        appointment_datetime: datetime,
        notes: str = "",
    ) -> Appointment:
        """Add a new scheduled appointment."""
        appt = Appointment(
            circle_id=circle_id,
            doctor=doctor,
            place=place,
            datetime=appointment_datetime,
            notes=notes,
        )
        await self.repos.appointments.save(appt.id, appt)
        return appt

    async def update_appointment(
        self,
        circle_id: str,
        appointment_id: str,
        doctor: str,
        place: str,
        appointment_datetime: datetime,
        notes: str = "",
    ) -> Appointment | None:
        """Update an existing appointment."""
        appt = await self.repos.appointments.get(appointment_id)
        if not appt or appt.circle_id != circle_id:
            return None

        appt.doctor = doctor
        appt.place = place
        appt.datetime = appointment_datetime
        appt.notes = notes
        await self.repos.appointments.save(appt.id, appt)
        return appt

    async def list_appointments(
        self, circle_id: str, upcoming_only: bool = False
    ) -> list[Appointment]:
        """List appointments for circle, optionally filtered to upcoming only."""
        now = datetime.now()
        appts = await self.repos.appointments.find(lambda a: a.circle_id == circle_id)

        if upcoming_only:
            appts = [a for a in appts if a.datetime >= now]

        appts.sort(key=lambda a: a.datetime)
        return appts

    async def get_appointment(self, circle_id: str, appointment_id: str) -> Appointment | None:
        """Fetch appointment by ID scoped to circle."""
        appt = await self.repos.appointments.get(appointment_id)
        if not appt or appt.circle_id != circle_id:
            return None
        return appt

    async def delete_appointment(self, circle_id: str, appointment_id: str) -> bool:
        """Delete an appointment scoped to circle."""
        appt = await self.repos.appointments.get(appointment_id)
        if not appt or appt.circle_id != circle_id:
            return False
        await self.repos.appointments.delete(appointment_id)
        return True
