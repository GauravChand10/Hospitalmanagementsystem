from datetime import datetime, timedelta

from django.utils import timezone

SLOT_LENGTH = timedelta(minutes=30)


def within_hours(doctor, day, start):
    """Require the whole appointment, not just its start, to fit working hours."""
    begins = datetime.combine(day, start)
    return any(
        datetime.combine(day, schedule.start_time) <= begins
        and begins + SLOT_LENGTH <= datetime.combine(day, schedule.end_time)
        for schedule in doctor.availability.filter(weekday=day.weekday())
    )


def available_slots(doctor, day):
    from billing.services import expire_holds
    expire_holds()
    schedules = list(doctor.availability.filter(weekday=day.weekday()))
    if not schedules:
        return []
    from appointments.models import Appointment
    occupied = set(Appointment.objects.filter(doctor=doctor, appointment_date=day).exclude(
        status=Appointment.Status.CANCELLED).values_list("appointment_time", flat=True))
    slots = []
    for schedule in schedules:
        current = datetime.combine(day, schedule.start_time)
        closing = datetime.combine(day, schedule.end_time)
        while current + SLOT_LENGTH <= closing:
            if current.time() not in occupied and timezone.make_aware(current) > timezone.now():
                slots.append(current.strftime("%H:%M"))
            current += SLOT_LENGTH
    return slots
